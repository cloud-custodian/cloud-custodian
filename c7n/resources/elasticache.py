# Copyright 2016 Capital One Services, LLC
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
from c7n import tags
from c7n.utils import (
    local_session, generate_arn,
    get_retry, chunks, snapshot_identifier, type_schema)

log = logging.getLogger('custodian.elasticache')

filters = FilterRegistry('elasticache.filters')
actions = ActionRegistry('elasticache.actions')

# registered marked-for-op filter
filters.register('marked-for-op', tags.TagActionFilter)

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

    filter_registry = filters
    action_registry = actions
    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('elasticache:ListTagsForResource',)

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

    def augment(self, clusters):
        filter(None, _elasticache_cluster_tags(
            self.get_model(),
            clusters, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return clusters


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].SecurityGroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):
    """Filters elasticache clusters based on their associated subnet

    :example:

        .. code-block: yaml

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


# added mark-for-op
@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

        .. code-block: yaml

            policies:
              - name: elasticache-mark-tag-compliance
                resource: cache-cluster
                filters:
                  - "tag:custodian_cleanup": absent
                  - "tag:OwnerName": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Cluster does not have valid OwnerName tag: {op}@{action_date}"
                    op: delete
                    days: 7
    """
    permission = ('elasticache:AddTagsToResource',)
    batch_size = 1

    def process_resource_set(self, clusters, tags):
        client = local_session(self.manager.session_factory).client(
            'elasticache')
        for cluster in clusters:
            arn = self.manager.generate_arn(cluster['CacheClusterId'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


# added unmark
@actions.register('remove-tag')
@actions.register('unmark')
class RemoveTag(tags.RemoveTag):
    """Action to remove tag(s) on a resource

    :example:

        .. code-block: yaml

            policies:
              - name: elasticache-remove-tags
                resource: cache-cluster
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('elasticache:RemoveTagsFromResource',)

    def process_resource_set(self, clusters, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elasticache')
        for cluster in clusters:
            arn = self.manager.generate_arn(cluster['CacheClusterId'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


@actions.register('delete')
class DeleteElastiCacheCluster(BaseAction):
    """Action to delete an elasticache cluster

    To prevent unwanted deletion of elasticache clusters, it is recommended
    to include a filter

    :example:

        .. code-block: yaml

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

        .. code-block: yaml

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
        with self.executor_factory(max_workers=3) as w:
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

    permissions = ('elasticache:ListTagsForResource',)
    filter_registry = FilterRegistry('elasticache-snapshot.filters')
    action_registry = ActionRegistry('elasticache-snapshot.actions')
    filter_registry.register('marked-for-op', tags.TagActionFilter)
    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))

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

    def augment(self, clusters):
        filter(None, _elasticache_snapshot_tags(
            self.get_model(),
            clusters, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return clusters


@ElastiCacheSnapshot.filter_registry.register('age')
class ElastiCacheSnapshotAge(AgeFilter):
    """Filters elasticache snapshots based on their age (in days)

    :example:

        .. code-block: yaml

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
        op={'type': 'string', 'enum': OPERATORS.keys()})

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

        .. code-block: yaml

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

# added mark-for-op


@ElastiCacheSnapshot.action_registry.register('mark-for-op')
class ElastiCacheSnapshotTagDelayedAction(tags.TagDelayedAction):
    """Action to specify a delayed action on an elasticache snapshot

    :example:

        .. code-block: yaml

            policies:
              - name: elasticache-stale-snapshots
                resource: cache-snapshot
                filters:
                  - "tag:custodian_cleanup": absent
                  - type: age
                    days: 23
                    op: eq
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    op: delete
                    days: 7
                    msg: "Expiring snapshot {op}@{action_date}"
    """

    batch_size = 1
    permissions = ('elasticache:AddTagsToResource',)

    def process_resource_set(self, snapshots, tags):
        client = local_session(
            self.manager.session_factory).client('elasticache')
        for snapshot in snapshots:
            arn = self.manager.generate_arn(snapshot['SnapshotName'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


@ElastiCacheSnapshot.action_registry.register('copy-cluster-tags')
class CopyClusterTags(BaseAction):
    """
    Copy specified tags from Elasticache cluster to Snapshot
    :example:

        .. code-block: yaml

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
        required = ('tags',))

    def get_permissions(self):
        perms = self.manager.get_resource_manager('cache-cluster').get_permissions()
        perms.append('elasticache:AddTagsToResource')
        return perms

    def process(self, snapshots):
        log.info("Modifying %d ElastiCache snapshots", len(snapshots))
        client = local_session(self.manager.session_factory).client('elasticache')
        clusters = {
            cluster['CacheClusterId']: cluster for cluster in
            self.manager.get_resource_manager('cache-cluster').resources()}

        for s in snapshots:
            if s['CacheClusterId'] in clusters:
                continue

            arn = self.manager.generate_arn(s['SnapshotName'])
            tags_cluster = clusters[s['CacheClusterId']]['Tags']
            only_tags = self.data.get('tags', [])  # Specify tags to copy
            extant_tags = {t['Key']: t['Value'] for t in s.get('Tags', ())}
            copy_tags = []

            for t in tags_cluster:
                if t['Key'] in only_tags and t['Value'] != extant_tags.get(t['Key'], ""):
                    copy_tags.append(t)
            self.retry(
                client.add_tags_to_resource, ResourceName=arn, Tags=copy_tags)

# added unmark


@ElastiCacheSnapshot.action_registry.register('remove-tag')
@ElastiCacheSnapshot.action_registry.register('unmark')
class ElastiCacheSnapshotRemoveTag(tags.RemoveTag):
    """Action to remove tag(s) from an elasticache snapshot

    :example:

        .. code-block: yaml

            policies:
              - name: cache-snapshot-remove-tags
                resource: cache-snapshot
                filters:
                  - "tag:UnusedTag": present
                actions:
                  - type: remove-tag
                    tags: ["UnusedTag"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('elasticache:RemoveTagsFromResource',)

    def process_resource_set(self, snapshots, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elasticache')
        for snapshot in snapshots:
            arn = self.manager.generate_arn(snapshot['SnapshotName'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


def _elasticache_cluster_tags(
        model, clusters, session_factory, executor_factory, generator, retry):
    """ Augment ElastiCache clusters with their respective tags
    """

    def process_tags(cluster):
        client = local_session(session_factory).client('elasticache')
        arn = generator(cluster[model.id])
        # added if statement to ensure snapshot is available in order to list tags
        if not cluster['CacheClusterStatus'] == 'available':
            return
        tag_list = retry(
            client.list_tags_for_resource,
            ResourceName=arn)['TagList']
        cluster['Tags'] = tag_list or []
        return cluster

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, clusters))


def _elasticache_snapshot_tags(
        model, snapshots, session_factory, executor_factory, generator, retry):
    """ Augment ElastiCache snapshots with their respective tags
    """

    # added if statement to ensure snapshot is available in order to list tags
    def process_tags(snapshot):
        client = local_session(session_factory).client('elasticache')
        arn = generator(snapshot[model.id])
        if not snapshot['SnapshotStatus'] == 'available':
            return
        tag_list = retry(
            client.list_tags_for_resource,
            ResourceName=arn)['TagList']
        snapshot['Tags'] = tag_list or []
        return snapshot

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, snapshots))


def _cluster_eligible_for_snapshot(cluster):
    # added regex search to filter unsupported cachenode types
    return (
        cluster['Engine'] != 'memcached' and not
        TTYPE.match(cluster['CacheNodeType'])
    )
