# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import functools
import logging
import re

from datetime import datetime

from concurrent.futures import as_completed
from dateutil.tz import tzutc
from dateutil.parser import parse

from c7n.actions import (
    ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction)
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import universal_augment
from c7n.utils import (
    local_session, generate_arn,
    get_retry, chunks, snapshot_identifier, type_schema)

log = logging.getLogger('custodian.elasticache')

filters = FilterRegistry('elasticache.filters')
actions = ActionRegistry('elasticache.actions')

TTYPE = re.compile('cache.t')


@resources.register('cache-cluster')
class ElastiCacheCluster(QueryResourceManager):

    class resource_type(object):
        service = 'elasticache'
        type = 'cluster'
        enum_spec = ('describe_cache_clusters',
                     'CacheClusters[]', None)
        name = id = 'CacheClusterId'
        filter_name = 'CacheClusterId'
        filter_type = 'scalar'
        date = 'CacheClusterCreateTime'
        dimension = 'CacheClusterId'
        universal_taggable = True

    filter_registry = filters
    action_registry = actions
    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('elasticache:ListTagsForResource',)
    augment = universal_augment

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'elasticache',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='cluster',
                separator=':')
        return self._generate_arn


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].SecurityGroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):
    """Filters elasticache clusters based on their associated subnet

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-in-subnet-x
                resource: cache-cluster
                filters:
                  - type: subnet
                    key: SubnetId
                    value: subnet-12ab34cd
    """

    RelatedIdsExpression = ""

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['CacheSubnetGroupName']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        self.groups = {
            r['CacheSubnetGroupName']: r for r in
            self.manager.get_resource_manager(
                'cache-subnet-group').resources()}
        return super(SubnetFilter, self).process(resources, event)


filters.register('network-location', net_filters.NetworkLocation)


@actions.register('delete')
class DeleteElastiCacheCluster(BaseAction):
    """Action to delete an elasticache cluster

    To prevent unwanted deletion of elasticache clusters, it is recommended
    to include a filter

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-delete-stale-clusters
                resource: cache-cluster
                filters:
                  - type: value
                    value_type: age
                    key: CacheClusterCreateTime
                    op: ge
                    value: 90
                actions:
                  - type: delete
                    skip-snapshot: false
    """

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})
    permissions = ('elasticache:DeleteCacheCluster',
                   'elasticache:DeleteReplicationGroup')

    def process(self, clusters):
        skip = self.data.get('skip-snapshot', False)
        client = local_session(
            self.manager.session_factory).client('elasticache')

        clusters_to_delete = []
        replication_groups_to_delete = set()
        for cluster in clusters:
            if cluster.get('ReplicationGroupId', ''):
                replication_groups_to_delete.add(cluster['ReplicationGroupId'])
            else:
                clusters_to_delete.append(cluster)
        # added if statement to handle differences in parameters if snapshot is skipped
        for cluster in clusters_to_delete:
            params = {'CacheClusterId': cluster['CacheClusterId']}
            if _cluster_eligible_for_snapshot(cluster) and not skip:
                params['FinalSnapshotIdentifier'] = snapshot_identifier(
                    'Final', cluster['CacheClusterId'])
                self.log.debug(
                    "Taking final snapshot of %s", cluster['CacheClusterId'])
            else:
                self.log.debug(
                    "Skipping final snapshot of %s", cluster['CacheClusterId'])
            client.delete_cache_cluster(**params)
            self.log.info(
                'Deleted ElastiCache cluster: %s',
                cluster['CacheClusterId'])

        for replication_group in replication_groups_to_delete:
            params = {'ReplicationGroupId': replication_group,
                      'RetainPrimaryCluster': False}
            if not skip:
                params['FinalSnapshotIdentifier'] = snapshot_identifier(
                    'Final', replication_group)
            client.delete_replication_group(**params)

            self.log.info(
                'Deleted ElastiCache replication group: %s',
                replication_group)


@actions.register('snapshot')
class SnapshotElastiCacheCluster(BaseAction):
    """Action to snapshot an elasticache cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-cluster-snapshot
                resource: cache-cluster
                filters:
                  - type: value
                    key: CacheClusterStatus
                    op: not-in
                    value: ["deleted","deleting","creating"]
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('elasticache:CreateSnapshot',)

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                if not _cluster_eligible_for_snapshot(cluster):
                    continue
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    cluster))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating cache cluster snapshot \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, cluster):
        c = local_session(self.manager.session_factory).client('elasticache')
        c.create_snapshot(
            SnapshotName=snapshot_identifier(
                'Backup',
                cluster['CacheClusterId']),
            CacheClusterId=cluster['CacheClusterId'])


@actions.register('modify-security-groups')
class ElasticacheClusterModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an Elasticache cluster.

    Looks at the individual clusters and modifies the Replication
    Group's configuration for Security groups so all nodes get
    affected equally

    """
    permissions = ('elasticache:ModifyReplicationGroup',)

    def process(self, clusters):
        replication_group_map = {}
        client = local_session(
            self.manager.session_factory).client('elasticache')
        groups = super(
            ElasticacheClusterModifyVpcSecurityGroups,
            self).get_groups(clusters, metadata_key='SecurityGroupId')
        for idx, c in enumerate(clusters):
            # build map of Replication Groups to Security Groups
            replication_group_map[c['ReplicationGroupId']] = groups[idx]

        for idx, r in enumerate(replication_group_map.keys()):
            client.modify_replication_group(
                ReplicationGroupId=r,
                SecurityGroupIds=replication_group_map[r])


@resources.register('cache-subnet-group')
class ElastiCacheSubnetGroup(QueryResourceManager):

    class resource_type(object):
        service = 'elasticache'
        type = 'subnet-group'
        enum_spec = ('describe_cache_subnet_groups',
                     'CacheSubnetGroups', None)
        name = id = 'CacheSubnetGroupName'
        filter_name = 'CacheSubnetGroupName'
        filter_type = 'scalar'
        date = None
        dimension = None


@resources.register('cache-snapshot')
class ElastiCacheSnapshot(QueryResourceManager):

    class resource_type(object):
        service = 'elasticache'
        type = 'snapshot'
        enum_spec = ('describe_snapshots', 'Snapshots', None)
        name = id = 'SnapshotName'
        filter_name = 'SnapshotName'
        filter_type = 'scalar'
        date = 'StartTime'
        dimension = None
        universal_taggable = True

    permissions = ('elasticache:ListTagsForResource',)
    filter_registry = FilterRegistry('elasticache-snapshot.filters')
    action_registry = ActionRegistry('elasticache-snapshot.actions')
    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))
    augment = universal_augment

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'elasticache',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='snapshot',
                separator=':')
        return self._generate_arn


@ElastiCacheSnapshot.filter_registry.register('age')
class ElastiCacheSnapshotAge(AgeFilter):
    """Filters elasticache snapshots based on their age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-stale-snapshots
                resource: cache-snapshot
                filters:
                  - type: age
                    days: 30
                    op: ge
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'type': 'string', 'enum': list(OPERATORS.keys())})

    date_attribute = 'dummy'

    def get_resource_date(self, snapshot):
        """ Override superclass method as there is no single snapshot date attribute.
        """
        def to_datetime(v):
            if not isinstance(v, datetime):
                v = parse(v)
            if not v.tzinfo:
                v = v.replace(tzinfo=tzutc())
            return v

        # Return the earliest of the node snaphot creation times.
        return min([to_datetime(ns['SnapshotCreateTime'])
                    for ns in snapshot['NodeSnapshots']])


@ElastiCacheSnapshot.action_registry.register('delete')
class DeleteElastiCacheSnapshot(BaseAction):
    """Action to delete elasticache snapshots

    To prevent unwanted deletion of elasticache snapshots, it is recommended to
    apply a filter

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-stale-snapshots
                resource: cache-snapshot
                filters:
                  - type: age
                    days: 30
                    op: ge
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('elasticache:DeleteSnapshot',)

    def process(self, snapshots):
        log.info("Deleting %d ElastiCache snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting snapshot set \n %s",
                            f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('elasticache')
        for s in snapshots_set:
            c.delete_snapshot(SnapshotName=s['SnapshotName'])


@ElastiCacheSnapshot.action_registry.register('copy-cluster-tags')
class CopyClusterTags(BaseAction):
    """
    Copy specified tags from Elasticache cluster to Snapshot
    :example:

    .. code-block:: yaml

            - name: elasticache-test
              resource: cache-snapshot
              filters:
                 - type: value
                   key: SnapshotName
                   op: in
                   value:
                    - test-tags-backup
              actions:
                - type: copy-cluster-tags
                  tags:
                    - tag1
                    - tag2
    """

    schema = type_schema(
        'copy-cluster-tags',
        tags={'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
        required=('tags',))

    def get_permissions(self):
        perms = self.manager.get_resource_manager('cache-cluster').get_permissions()
        perms.append('elasticache:AddTagsToResource')
        return perms

    def process(self, snapshots):
        client = local_session(self.manager.session_factory).client('elasticache')
        clusters = {r['CacheClusterId']: r for r in
                    self.manager.get_resource_manager('cache-cluster').resources()}
        copyable_tags = self.data.get('tags')

        for s in snapshots:
            # For replicated/sharded clusters it is possible for each
            # shard to have separate tags, we go ahead and tag the
            # snap with the union of tags with overlaps getting the
            # last value (arbitrary if mismatched).
            if 'CacheClusterId' not in s:
                cluster_ids = [ns['CacheClusterId'] for ns in s['NodeSnapshots']]
            else:
                cluster_ids = [s['CacheClusterId']]

            copy_tags = {}
            for cid in sorted(cluster_ids):
                if cid not in clusters:
                    continue

                cluster_tags = {t['Key']: t['Value'] for t in clusters[cid]['Tags']}
                snap_tags = {t['Key']: t['Value'] for t in s.get('Tags', ())}

                for k, v in cluster_tags.items():
                    if copyable_tags and k not in copyable_tags:
                        continue
                    if k.startswith('aws:'):
                        continue
                    if snap_tags.get(k, '') == v:
                        continue
                    copy_tags[k] = v

            if not copy_tags:
                continue

            if len(set(copy_tags).union(set(snap_tags))) > 50:
                self.log.error(
                    "Cant copy tags, max tag limit hit on snapshot:%s",
                    s['SnapshotName'])
                continue

            arn = self.manager.generate_arn(s['SnapshotName'])
            self.manager.retry(
                client.add_tags_to_resource,
                ResourceName=arn,
                Tags=[{'Key': k, 'Value': v} for k, v in copy_tags.items()])


def _cluster_eligible_for_snapshot(cluster):
    # added regex search to filter unsupported cachenode types
    return (
        cluster['Engine'] != 'memcached' and not
        TTYPE.match(cluster['CacheNodeType'])
    )
