# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import c7n.filters.vpc as net_filters
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import (
    ConfigSource,
    DescribeSource,
    DescribeWithResourceTags,
    QueryResourceManager,
    TypeInfo,
)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema

from .aws import AWS


class DescribeMemoryDb(DescribeSource):

    def augment(self, resources):
        resources = super(DescribeMemoryDb, self).augment(resources)
        client = local_session(self.manager.session_factory).client('memorydb')
        results = []
        for r in resources:
            r['Tags'] = self.manager.retry(
                    client.list_tags, ResourceArn=r['ARN']).get('TagList', [])
            results.append(r)
        return results


@AWS.resources.register('memorydb')
class MemoryDb(QueryResourceManager):
    """AWS MemoryDb

    https://docs.aws.amazon.com/memorydb/latest/devguide/what-is-memorydb-for-redis.html
    """

    class resource_type(TypeInfo):

        service = 'memorydb'
        enum_spec = ('describe_clusters', 'Clusters', None)
        arn = 'ARN'
        arn_type = 'cluster'
        id = name = 'Name'
        cfn_type = 'AWS::MemoryDB::Cluster'
        permission_prefix = 'memorydb'

    source_mapping = {'describe': DescribeMemoryDb}


@resources.register('memorydb-snapshot')
class MemoryDbSnapshot(QueryResourceManager):
    """AWS MemoryDb Snapshot

    https://docs.aws.amazon.com/memorydb/latest/devguide/snapshots.html
    """

    class resource_type(TypeInfo):

        service = 'memorydb'
        enum_spec = ('describe_snapshots', 'Snapshots', None)
        arn = 'ARN'
        arn_type = 'snapshot'
        filter_name = "Name"
        filter_type = "scalar"
        id = name = 'Name'
        permission_prefix = 'memorydb'

    source_mapping = {'describe': DescribeMemoryDb}


@resources.register('memorydb-user')
class MemoryDbUser(QueryResourceManager):
    """AWS MemoryDb

    https://docs.aws.amazon.com/memorydb/latest/devguide/what-is-memorydb-for-redis.html
    """

    class resource_type(TypeInfo):

        service = 'memorydb'
        enum_spec = ('describe_users', 'Users', None)
        arn = 'ARN'
        arn_type = 'user'
        id = name = 'Name'
        cfn_type = 'AWS::MemoryDB::User'
        permission_prefix = 'memorydb'

    source_mapping = {'describe': DescribeMemoryDb}


@resources.register('memorydb-acl')
class MemoryDbAcl(QueryResourceManager):
    """AWS MemoryDb

    https://docs.aws.amazon.com/memorydb/latest/devguide/what-is-memorydb-for-redis.html
    """

    class resource_type(TypeInfo):

        service = 'memorydb'
        enum_spec = ('describe_acls', 'ACLs', None)
        arn = 'ARN'
        arn_type = 'acl'
        id = name = 'Name'
        cfn_type = 'AWS::MemoryDB::ACL'
        permission_prefix = 'memorydb'

    source_mapping = {'describe': DescribeMemoryDb}


@MemoryDb.action_registry.register('tag')
@MemoryDbSnapshot.action_registry.register('tag')
@MemoryDbUser.action_registry.register('tag')
@MemoryDbAcl.action_registry.register('tag')
class TagMemoryDb(Tag):
    """Create tags on MemoryDb

    :example:

    .. code-block:: yaml

        policies:
            - name: memory-db-tag
              resource: aws.memorydb
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('memorydb:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            try:
                client.tag_resource(ResourceArn=r["ARN"], Tags=new_tags)
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.SnapshotNotFoundFault,
                    client.exceptions.UserNotFoundFault,
                    client.exceptions.ACLNotFoundFault):
                continue


@MemoryDb.action_registry.register('remove-tag')
@MemoryDbSnapshot.action_registry.register('remove-tag')
@MemoryDbUser.action_registry.register('remove-tag')
@MemoryDbAcl.action_registry.register('remove-tag')
class RemoveMemoryDbTag(RemoveTag):
    """Remove tags from a memorydb cluster
    :example:

    .. code-block:: yaml

        policies:
            - name: memorydb-remove-tag
              resource: aws.memorydb
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('memorydb:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            try:
                client.untag_resource(ResourceArn=r['ARN'], TagKeys=tags)
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.SnapshotNotFoundFault,
                    client.exceptions.UserNotFoundFault,
                    client.exceptions.ACLNotFoundFault):
                continue


MemoryDb.filter_registry.register('marked-for-op', TagActionFilter)
MemoryDb.action_registry.register('mark-for-op', TagDelayedAction)
MemoryDbSnapshot.filter_registry.register('marked-for-op', TagActionFilter)
MemoryDbSnapshot.action_registry.register('mark-for-op', TagDelayedAction)
MemoryDbUser.filter_registry.register('marked-for-op', TagActionFilter)
MemoryDbUser.action_registry.register('mark-for-op', TagDelayedAction)
MemoryDbAcl.filter_registry.register('marked-for-op', TagActionFilter)
MemoryDbAcl.action_registry.register('mark-for-op', TagDelayedAction)


@MemoryDb.action_registry.register('delete')
class DeleteMemoryDbCluster(BaseAction):
    """Delete a memorydb cluster

    :example:

    .. code-block:: yaml

        policies:
          - name: memorydb-delete
            resource: aws.memorydb
            actions:
              - type: delete
                FinalSnapshotName: test-snapshot
    """
    schema = type_schema('delete', FinalSnapshotName={'type': 'string'})
    permissions = ('memorydb:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('memorydb')
        FinalSnapshotName = self.data.get('FinalSnapshotName', '')
        for r in resources:
            try:
                client.delete_cluster(
                    ClusterName=r['Name'],
                    FinalSnapshotName=FinalSnapshotName
                )
            except client.exceptions.ClusterNotFoundFault:
                continue


@MemoryDb.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@MemoryDb.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].SecurityGroupId"


MemoryDb.filter_registry.register('network-location', net_filters.NetworkLocation)


@MemoryDb.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):
    """Filters memorydb clusters based on their associated subnet

    :example:

    .. code-block:: yaml

            policies:
              - name: memorydb-in-subnet-x
                resource: memorydb
                filters:
                  - type: subnet
                    key: SubnetId
                    value: subnet-12ab34cd
    """

    RelatedIdsExpression = ""

    def get_subnet_groups(self):
        return {
            r['Name']: r for r in
            self.manager.get_resource_manager('memorydb-subnet-group').resources()}

    def get_related_ids(self, resources):
        if not hasattr(self, 'groups'):
            self.groups = self.get_subnet_groups()
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['Identifier'] for s in
                 self.groups[r['SubnetGroupName']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        self.groups = {
            r['Name']: r for r in
            self.manager.get_resource_manager(
                'memorydb-subnet-group').resources()}
        return super(SubnetFilter, self).process(resources, event)


@resources.register('memorydb-subnet-group')
class MemoryDbSubnetGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'memorydb'
        arn_type = 'subnetgroup'
        enum_spec = ('describe_subnet_groups',
                     'SubnetGroups', None)
        name = id = 'Name'
        filter_name = 'SubnetGroupName'
        filter_type = 'scalar'
        config_type = cfn_type = 'AWS::MemoryDB::SubnetGroup'
        universal_taggable = object()
        permissions = ('memorydb:DescribeSubnetGroups',)

    source_mapping = {
        'describe': DescribeWithResourceTags,
        'config': ConfigSource
    }


@MemoryDbSnapshot.action_registry.register('delete')
class DeleteMemoryDbSnapshot(BaseAction):
    """Delete a memorydb cluster snapshot

    :example:

    .. code-block:: yaml

        policies:
          - name: memorydb-snapshot-delete
            resource: aws.memorydb-snapshot
            actions:
              - type: delete
    """
    schema = type_schema('delete', FinalSnapshotName={'type': 'string'})
    permissions = ('memorydb:DeleteSnapshot',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('memorydb')
        for r in resources:
            try:
                client.delete_snapshot(
                    SnapshotName=r['Name'],
                )
            except client.exceptions.SnapshotNotFoundFault:
                continue


@MemoryDbUser.action_registry.register('delete')
class DeleteMemoryDbUser(BaseAction):
    """Delete a memorydb user

    :example:

    .. code-block:: yaml

        policies:
          - name: memorydb-user-delete
            resource: aws.memorydb-user
            actions:
              - type: delete
    """
    schema = type_schema('delete',)
    permissions = ('memorydb:DeleteUser',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('memorydb')
        for r in resources:
            try:
                client.delete_user(
                    UserName=r['Name'],
                )
            except client.exceptions.UserNotFoundFault:
                continue


@MemoryDbAcl.action_registry.register('delete')
class DeleteMemoryDbAcl(BaseAction):
    """Delete a memorydb acl

    :example:

    .. code-block:: yaml

        policies:
          - name: memorydb-acl-delete
            resource: aws.memorydb-acl
            actions:
              - type: delete
    """
    schema = type_schema('delete',)
    permissions = ('memorydb:DeleteAcl',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('memorydb')
        for r in resources:
            try:
                client.delete_acl(
                    ACLName=r['Name'],
                )
            except client.exceptions.ACLNotFoundFault:
                continue
