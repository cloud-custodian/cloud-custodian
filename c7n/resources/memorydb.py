# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .aws import AWS
from c7n.query import (
    QueryResourceManager, TypeInfo, DescribeSource)
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction


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
        arn_type = 'memorydb'
        id = name = 'Name'
        cfn_type = 'AWS::MemoryDB::Cluster'
        permission_prefix = 'memorydb'

    source_mapping = {'describe': DescribeMemoryDb}


@MemoryDb.action_registry.register('tag')
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
            client.tag_resource(ResourceArn=r["ARN"], Tags=new_tags)


@MemoryDb.action_registry.register('remove-tag')
class RemoveMemoryDb(RemoveTag):
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
            client.untag_resource(ResourceArn=r['ARN'], TagKeys=tags)


@MemoryDb.filter_registry.register('marked-for-op', TagActionFilter)


@MemoryDb.action_registry.register('mark-for-op')
class MarkMemoryDbForOp(TagDelayedAction):
    """Mark memorydb for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: memorydb-tag-mark
            resource: aws.memorydb
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@MemoryDb.action_registry.register('delete')
class DeleteMemoryDb(BaseAction):
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

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('memorydb')
        FinalSnapshotName = self.data.get('FinalSnapshotName', '')
        for r in resources:
            try:
                client.delete_cluster(
                    ClusterName=r['Name'],
                    FinalSnapshotName=FinalSnapshotName
                )
            except client.exceptions.ResourceNotFoundException:
                continue
