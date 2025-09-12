# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
import re

from concurrent.futures import as_completed
from dateutil.tz import tzutc
from dateutil.parser import parse

from c7n.actions import (
    ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction)
from c7n.filters import FilterRegistry, AgeFilter
import c7n.filters.vpc as net_filters
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import universal_augment
from c7n.utils import (
    local_session, chunks, snapshot_identifier, type_schema, jmespath_search,
    get_retry, QueryParser)

from .aws import shape_validate

filters = FilterRegistry('elasticache.filters')
actions = ActionRegistry('elasticache.actions')

TTYPE = re.compile('cache.t1')


class ElastiCacheQueryParser(QueryParser):

    QuerySchema = {
        'ShowCacheNodeInfo': bool,
        'ShowCacheClustersNotInReplicationGroups': bool,
    }
    multi_value = False
    value_key = 'Value'


class DescribeElastiCache(DescribeSource):
    """
    Allows to use query to retrieve more information

    :example

    .. code-block:: yaml

        policies:
          - name: cache-node-with-default-port
            resource: aws.cache-cluster
            query:
              - Name: ShowCacheNodeInfo
                Value: true
            filters:
              - type: list-item
                key: CacheNodes
                attrs:
                  - type: value
                    key: Endpoint.Port
                    value: 11211
    """

    def get_query_params(self, query_params):
        query_params = query_params or {}
        for q in ElastiCacheQueryParser.parse(self.manager.data.get('query', [])):
            query_params[q['Name']] = q['Value']
        return query_params


@resources.register('cache-cluster')
class ElastiCacheCluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'elasticache'
        arn_type = 'cluster'
        arn_separator = ":"
        enum_spec = ('describe_cache_clusters',
                     'CacheClusters[]', None)
        name = id = 'CacheClusterId'
        filter_name = 'CacheClusterId'
        filter_type = 'scalar'
        date = 'CacheClusterCreateTime'
        dimension = 'CacheClusterId'
        universal_taggable = True
        cfn_type = 'AWS::ElastiCache::CacheCluster'
        permissions_augment = ("elasticache:ListTagsForResource",)

    filter_registry = filters
    action_registry = actions
    permissions = ('elasticache:ListTagsForResource',)
    augment = universal_augment

    source_mapping = {
        'describe': DescribeElastiCache,
        'config': ConfigSource
    }


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


@filters.register('vpc')
class VpcFilter(net_filters.VpcFilter):
    """Filters elasticache clusters based on their associated VPCs

    :example:

    .. code-block:: yaml

        policies:
          - name: cache-node-with-default-vpc
            resource: aws.cache-cluster
            filters:
              - type: vpc
                key: IsDefault
                value: false
    """

    RelatedIdsExpression = ""

    def get_related_ids(self, resources):
        return {
            self.groups[res['CacheSubnetGroupName']]['VpcId'] for res in resources
        }

    def process(self, resources, event=None):
        self.groups = {
            r['CacheSubnetGroupName']: r
            for r in self.manager.get_resource_manager('cache-subnet-group').resources()
        }
        return super().process(resources, event)


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
            if cluster.get('ReplicationGroupId') in self.fetch_global_ds_rpgs():
                self.log.info(
                  f"Skipping {cluster['CacheClusterId']}: associated with a global datastore")
                continue
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

        cacheClusterIds = set([c["CacheClusterId"] for c in clusters])
        for replication_group in replication_groups_to_delete:
            # NOTE don't delete the group if it's not empty
            rg = client.describe_replication_groups(
                ReplicationGroupId=replication_group)["ReplicationGroups"][0]
            if not all(cluster in cacheClusterIds for cluster in rg["MemberClusters"]):
                # NOTE mark members for better presentation on notifications
                for c in clusters:
                    if c.get("ReplicationGroupId") == replication_group:
                        c["MemberClusters"] = rg["MemberClusters"]
                self.log.info(f'{replication_group} is not empty: {rg["MemberClusters"]}')
                continue

            params = {'ReplicationGroupId': replication_group,
                      'RetainPrimaryCluster': False}
            if not skip:
                params['FinalSnapshotIdentifier'] = snapshot_identifier(
                    'Final', replication_group)
            client.delete_replication_group(**params)

            self.log.info(
                'Deleted ElastiCache replication group: %s',
                replication_group)

    def fetch_global_ds_rpgs(self):
        rpgs = self.manager.get_resource_manager('elasticache-group').resources(augment=False)
        global_rpgs = get_global_datastore_association(rpgs)
        return global_rpgs


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
        set_size = len(clusters)
        clusters = [c for c in clusters if _cluster_eligible_for_snapshot(c)]
        if set_size != len(clusters):
            self.log.info(
                "action:snapshot implicitly filtered from %d to %d clusters for snapshot support",
                set_size, len(clusters))

        with self.executor_factory(max_workers=2) as w:
            futures = []
            client = local_session(self.manager.session_factory).client('elasticache')
            for cluster in clusters:
                futures.append(
                    w.submit(self.process_cluster_snapshot, client, cluster))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating cache cluster snapshot \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, client, cluster):
        client.create_snapshot(
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
            ElasticacheClusterModifyVpcSecurityGroups, self).get_groups(
                clusters)
        for idx, c in enumerate(clusters):
            # build map of Replication Groups to Security Groups
            replication_group_map[c['ReplicationGroupId']] = groups[idx]

        for idx, r in enumerate(replication_group_map.keys()):
            client.modify_replication_group(
                ReplicationGroupId=r,
                SecurityGroupIds=replication_group_map[r])


@resources.register('cache-subnet-group')
class ElastiCacheSubnetGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'elasticache'
        arn_type = 'subnetgroup'
        enum_spec = ('describe_cache_subnet_groups',
                     'CacheSubnetGroups', None)
        name = id = 'CacheSubnetGroupName'
        filter_name = 'CacheSubnetGroupName'
        filter_type = 'scalar'
        cfn_type = 'AWS::ElastiCache::SubnetGroup'


@resources.register('cache-snapshot')
class ElastiCacheSnapshot(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'elasticache'
        arn_type = 'snapshot'
        arn_separator = ":"
        enum_spec = ('describe_snapshots', 'Snapshots', None)
        name = id = 'SnapshotName'
        filter_name = 'SnapshotName'
        filter_type = 'scalar'
        date = 'StartTime'
        universal_taggable = True

    permissions = ('elasticache:ListTagsForResource',)

    def augment(self, resources):
        return universal_augment(self, resources)


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
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

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
              - name: delete-elasticache-stale-snapshots
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
        self.log.info("Deleting %d ElastiCache snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            client = local_session(self.manager.session_factory).client('elasticache')
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, client, snapshot_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting snapshot set \n %s",
                            f.exception())
        return snapshots

    def process_snapshot_set(self, client, snapshots_set):
        for s in snapshots_set:
            client.delete_snapshot(SnapshotName=s['SnapshotName'])


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


@resources.register('elasticache-group')
class ElastiCacheReplicationGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "elasticache"
        enum_spec = ('describe_replication_groups',
                     'ReplicationGroups[]', None)
        arn_type = 'replicationgroup'
        id = name = dimension = 'ReplicationGroupId'
        cfn_type = 'AWS::ElastiCache::ReplicationGroup'
        arn_separator = ":"
        universal_taggable = object()

    augment = universal_augment
    permissions = ('elasticache:DescribeReplicationGroups',)


@ElastiCacheReplicationGroup.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


def get_global_datastore_association(resources):
    global_ds_rpgs = set()
    for r in resources:
        global_ds_association = jmespath_search(
            'GlobalReplicationGroupInfo.GlobalReplicationGroupId', r)
        if global_ds_association:
            global_ds_rpgs.add(r['ReplicationGroupId'])
    return global_ds_rpgs


@ElastiCacheReplicationGroup.action_registry.register('delete')
class DeleteReplicationGroup(BaseAction):
    """Action to delete a cache replication group

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-delete-replication-group
                resource: aws.elasticache-group
                filters:
                  - type: value
                    key: AtRestEncryptionEnabled
                    value: False
                actions:
                  - type: delete
                    snapshot: False

    """
    schema = type_schema(
        'delete', **{'snapshot': {'type': 'boolean'}})

    valid_origin_states = ('available',)
    permissions = ('elasticache:DeleteReplicationGroup',)

    def process(self, resources):
        resources = self.filter_resources(resources, 'Status', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('elasticache')
        global_datastore_association_map = get_global_datastore_association(resources)
        for r in resources:
            if r['ReplicationGroupId'] in global_datastore_association_map:
                self.log.info(
                  f"Skipping {r['ReplicationGroupId']}: associated with a global datastore")
                continue
            params = {'ReplicationGroupId': r['ReplicationGroupId']}
            if self.data.get('snapshot', False):
                params.update({'FinalSnapshotIdentifier': r['ReplicationGroupId'] + '-snapshot'})
            self.manager.retry(client.delete_replication_group, **params, ignore_err_codes=(
                'ReplicationGroupNotFoundFault',))


@resources.register('elasticache-user')
class ElastiCacheUser(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'elasticache'
        enum_spec = ('describe_users', 'Users[]', None)
        arn_separator = ":"
        arn_type = 'user'
        arn = 'ARN'
        id = 'UserId'
        name = 'UserName'
        cfn_type = 'AWS::ElastiCache::User'
        universal_taggable = object()

    augment = universal_augment
    permissions = ('elasticache:DescribeUsers',)


@ElastiCacheUser.action_registry.register('delete')
class DeleteUser(BaseAction):
    """Action to delete a cache user

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-delete-user
                resource: aws.elasticache-user
                filters:
                  - type: value
                    key: Authentication.Type
                    value: no-password
                actions:
                  - delete

    """
    schema = type_schema('delete')

    permissions = ('elasticache:DeleteUser',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elasticache')
        retry = get_retry(('ThrottlingException', 'InvalidUserStateFault'))
        for r in resources:
            retry(client.delete_user, UserId=r['UserId'], ignore_err_codes=('UserNotFoundFault',))


@ElastiCacheUser.action_registry.register('modify')
class ModifyUser(BaseAction):
    """Action to modify a cache user

    :example:

    .. code-block:: yaml

            policies:
              - name: elasticache-modify-user
                resource: aws.elasticache-user
                filters:
                  - type: value
                    key: Authentication.Type
                    value: no-password
                actions:
                  - type: modify
                    attributes:
                      AuthenticationMode:
                        Type: password
                        Passwords:
                          - "password"
    """

    permissions = ('elasticache:ModifyUser',)
    schema = type_schema(
        'modify',
        attributes={'type:': 'object'},
        required=('attributes',))
    shape = 'ModifyUserMessage'

    def validate(self):
        req = dict(self.data["attributes"])
        req["UserId"] = "validate"
        return shape_validate(
            req, self.shape, self.manager.resource_type.service
        )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elasticache')
        retry = get_retry(('ThrottlingException', 'InvalidUserStateFault'))
        for r in resources:
            retry(client.modify_user, UserId=r['UserId'], **self.data["attributes"],
                ignore_err_codes=('UserNotFoundFault',))
