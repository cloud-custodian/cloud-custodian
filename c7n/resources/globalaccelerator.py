# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .aws import AWS
from c7n.query import (
    QueryResourceManager, TypeInfo, DescribeSource)
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.filters.kms import KmsRelatedFilter
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.tags import universal_augment


GlobalAccelerator_REGION = 'us-west-2'


@AWS.resources.register('globalaccelerator')
class GlobalAccelerator(QueryResourceManager):
    """AWS Global Accelerator

    https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html
    """

    class resource_type(TypeInfo):

        service = 'globalaccelerator'
        enum_spec = ('list_accelerators', 'Accelerators', None)
        detail_spec = (
            'describe_accelerator', 'AcceleratorArn', 'AcceleratorArn', 'Accelerator')
        arn = id = 'AcceleratorArn'
        # name = 'TrainingJobName'
        # date = 'CreationTime'
        # permission_augment = (
        #     'sagemaker:DescribeTrainingJob', 'sagemaker:ListTags')

        # enum_spec = ('describe_clusters', 'Clusters', None)
        # arn = 'ARN'
        # arn_type = 'cluster'
        # id = name = 'Name'
        #universal_taggable = object()
        cfn_type = 'AWS::GlobalAccelerator::Accelerator'
        permission_prefix = 'globalaccelerator'

    def augment(self, resources):
        client = self.get_client()

        def _augment(r):
            r['Tags'] = self.retry(client.list_tags_for_resource,
                ResourceArn=r['AcceleratorArn'])['Tags']
            #r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in tags]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))

    def get_client(self):
        return local_session(self.session_factory) \
            .client('globalaccelerator', region_name=GlobalAccelerator_REGION)



# @resources.register('memorydb-snapshot')
# class MemoryDbSnapshot(QueryResourceManager):
#     """AWS MemoryDb Snapshot

#     https://docs.aws.amazon.com/memorydb/latest/devguide/snapshots.html
#     """

#     class resource_type(TypeInfo):

#         service = 'memorydb'
#         enum_spec = ('describe_snapshots', 'Snapshots', None)
#         arn = 'ARN'
#         arn_type = 'snapshot'
#         filter_name = "Name"
#         filter_type = "scalar"
#         id = name = 'Name'
#         permission_prefix = 'memorydb'

#     source_mapping = {'describe': DescribeMemoryDb}


@GlobalAccelerator.action_registry.register('tag')
class TagGlobalAccelerator(Tag):
    """Create tags on Global Accelerator

    :example:

    .. code-block:: yaml

        policies:
            - name: globalaccelerator-db-tag
              resource: aws.globalaccelerator
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('globalaccelerator:TagResource',)

    def get_client(self):
        return self.manager.get_client()

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            try:
                client.tag_resource(ResourceArn=r["AcceleratorArn"], Tags=new_tags)
            except client.exceptions.AcceleratorNotFoundException:
                continue


@GlobalAccelerator.action_registry.register('remove-tag')
class RemoveGlobalAcceleratorTag(RemoveTag):
    """Remove tags from a global accelerator
    :example:

    .. code-block:: yaml

        policies:
            - name: globalaccelerator-remove-tag
              resource: aws.globalaccelerator
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('globalaccelerator:UntagResource',)

    def get_client(self):
        return self.manager.get_client()

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            try:
                client.untag_resource(ResourceArn=r['AcceleratorArn'], TagKeys=tags)
            except client.exceptions.AcceleratorNotFoundException:
                continue


GlobalAccelerator.filter_registry.register('marked-for-op', TagActionFilter)
GlobalAccelerator.action_registry.register('mark-for-op', TagDelayedAction)
GlobalAccelerator.filter_registry.register('marked-for-op', TagActionFilter)
GlobalAccelerator.action_registry.register('mark-for-op', TagDelayedAction)


# @MemoryDb.action_registry.register('delete')
# class DeleteMemoryDbCluster(BaseAction):
#     """Delete a memorydb cluster

#     :example:

#     .. code-block:: yaml

#         policies:
#           - name: memorydb-delete
#             resource: aws.memorydb
#             actions:
#               - type: delete
#                 FinalSnapshotName: test-snapshot
#     """
#     schema = type_schema('delete', FinalSnapshotName={'type': 'string'})
#     permissions = ('memorydb:DeleteCluster',)

#     def process(self, resources):
#         client = local_session(self.manager.session_factory).client('memorydb')
#         FinalSnapshotName = self.data.get('FinalSnapshotName', '')
#         for r in resources:
#             try:
#                 client.delete_cluster(
#                     ClusterName=r['Name'],
#                     FinalSnapshotName=FinalSnapshotName
#                 )
#             except client.exceptions.ClusterNotFoundFault:
#                 continue


# @MemoryDb.filter_registry.register('kms-key')
# class KmsFilter(KmsRelatedFilter):

#     RelatedIdsExpression = 'KmsKeyId'


# @MemoryDb.filter_registry.register('security-group')
# class SecurityGroupFilter(net_filters.SecurityGroupFilter):

#     RelatedIdsExpression = "SecurityGroups[].SecurityGroupId"


# MemoryDb.filter_registry.register('network-location', net_filters.NetworkLocation)


# @MemoryDb.filter_registry.register('subnet')
# class SubnetFilter(net_filters.SubnetFilter):
#     """Filters memorydb clusters based on their associated subnet

#     :example:

#     .. code-block:: yaml

#             policies:
#               - name: memorydb-in-subnet-x
#                 resource: memorydb
#                 filters:
#                   - type: subnet
#                     key: SubnetId
#                     value: subnet-12ab34cd
#     """

#     RelatedIdsExpression = ""

#     def get_subnet_groups(self):
#         return {
#             r['Name']: r for r in
#             self.manager.get_resource_manager('memorydb-subnet-group').resources()}

#     def get_related_ids(self, resources):
#         if not hasattr(self, 'groups'):
#             self.groups = self.get_subnet_groups()
#         group_ids = set()
#         for r in resources:
#             group_ids.update(
#                 [s['Identifier'] for s in
#                  self.groups[r['SubnetGroupName']]['Subnets']])
#         return group_ids

#     def process(self, resources, event=None):
#         self.groups = {
#             r['Name']: r for r in
#             self.manager.get_resource_manager(
#                 'memorydb-subnet-group').resources()}
#         return super(SubnetFilter, self).process(resources, event)


# @resources.register('memorydb-subnet-group')
# class MemoryDbSubnetGroup(QueryResourceManager):

#     class resource_type(TypeInfo):
#         service = 'memorydb'
#         arn_type = 'subnetgroup'
#         enum_spec = ('describe_subnet_groups',
#                      'SubnetGroups', None)
#         name = id = 'Name'
#         filter_name = 'SubnetGroupName'
#         filter_type = 'scalar'
#         cfn_type = 'AWS::MemoryDB::SubnetGroup'
#         universal_taggable = object()
#         permissions = ('memorydb:DescribeSubnetGroups',)
#     augment = universal_augment


# @MemoryDbSnapshot.action_registry.register('delete')
# class DeleteMemoryDbSnapshot(BaseAction):
#     """Delete a memorydb cluster snapshot

#     :example:

#     .. code-block:: yaml

#         policies:
#           - name: memorydb-snapshot-delete
#             resource: aws.memorydb-snapshot
#             actions:
#               - type: delete
#     """
#     schema = type_schema('delete', FinalSnapshotName={'type': 'string'})
#     permissions = ('memorydb:DeleteSnapshot',)

#     def process(self, resources):
#         client = local_session(self.manager.session_factory).client('memorydb')
#         for r in resources:
#             try:
#                 client.delete_snapshot(
#                     SnapshotName=r['Name'],
#                 )
#             except client.exceptions.SnapshotNotFoundFault:
#                 continue
