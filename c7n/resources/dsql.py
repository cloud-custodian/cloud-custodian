# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import (
    ChildDescribeSource,
    ChildResourceManager,
    DescribeWithResourceTags,
    QueryResourceManager,
    TypeInfo,
)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment
from c7n.utils import get_retry, local_session, type_schema


dsql_retry = get_retry((
    'ThrottlingException',
    'InternalServerException',
    'ConflictException',
))


@resources.register('dsql-cluster')
class DsqlCluster(QueryResourceManager):
    """Amazon Aurora DSQL Cluster.

    :example:

    .. code-block:: yaml

        policies:
          - name: dsql-cluster-without-deletion-protection
            resource: aws.dsql-cluster
            filters:
              - deletionProtectionEnabled: false
    """

    class resource_type(TypeInfo):
        service = 'dsql'
        enum_spec = ('list_clusters', 'clusters', None)
        detail_spec = ('get_cluster', 'identifier', 'identifier', None)
        id = 'identifier'
        name = 'identifier'
        arn = 'arn'
        arn_type = 'cluster'
        date = 'creationTime'

    retry = staticmethod(dsql_retry)
    source_mapping = {'describe': DescribeWithResourceTags}


DsqlCluster.filter_registry.register('marked-for-op', TagActionFilter)


@DsqlCluster.action_registry.register('tag')
class TagDsqlCluster(Tag):
    permissions = ('dsql:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {t['Key']: t['Value'] for t in new_tags}
        for r in resources:
            client.tag_resource(resourceArn=r['arn'], tags=tags)


@DsqlCluster.action_registry.register('remove-tag')
class RemoveTagDsqlCluster(RemoveTag):
    permissions = ('dsql:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            client.untag_resource(resourceArn=r['arn'], tagKeys=tag_keys)


DsqlCluster.action_registry.register('mark-for-op', TagDelayedAction)


@DsqlCluster.filter_registry.register('cross-account')
class DsqlClusterCrossAccount(CrossAccountAccessFilter):
    """Check a DSQL cluster's resource-based policy for cross-account access.

    :example:

    .. code-block:: yaml

        policies:
          - name: dsql-cluster-cross-account
            resource: aws.dsql-cluster
            filters:
              - type: cross-account
    """
    policy_attribute = 'c7n:Policy'
    permissions = ('dsql:GetClusterPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('dsql')
        for r in resources:
            if self.policy_attribute in r:
                continue
            try:
                result = self.manager.retry(
                    client.get_cluster_policy, identifier=r['identifier'])
            except ClientError as e:
                code = e.response['Error']['Code']
                if code == 'ResourceNotFoundException':
                    r[self.policy_attribute] = None
                    continue
                raise
            r[self.policy_attribute] = result.get('policy')
        return super().process(resources, event)


@DsqlCluster.action_registry.register('delete')
class DeleteDsqlCluster(BaseAction):
    """Delete a DSQL cluster.

    Set ``force: true`` to disable deletion protection on clusters that have
    it enabled before issuing the delete call.

    :example:

    .. code-block:: yaml

        policies:
          - name: dsql-cluster-delete-unowned
            resource: aws.dsql-cluster
            filters:
              - "tag:Owner": absent
            actions:
              - type: delete
                force: true
    """
    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('dsql:DeleteCluster', 'dsql:UpdateCluster')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dsql')
        force = self.data.get('force', False)
        for r in resources:
            try:
                if force and r.get('deletionProtectionEnabled'):
                    self.manager.retry(
                        client.update_cluster,
                        identifier=r['identifier'],
                        deletionProtectionEnabled=False)
                self.manager.retry(
                    client.delete_cluster, identifier=r['identifier'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    continue
                raise


class DescribeStream(ChildDescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('dsql')
        results = []
        for r in resources:
            try:
                detail = self.manager.retry(
                    client.get_stream,
                    clusterIdentifier=r['clusterIdentifier'],
                    streamIdentifier=r['streamIdentifier'])
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise
                self.manager.log.warning(
                    "Resource not found: get_stream using %s" % {
                        'clusterIdentifier': r['clusterIdentifier'],
                        'streamIdentifier': r['streamIdentifier']})
                continue
            detail.pop('ResponseMetadata', None)
            r.update(detail)
            results.append(r)
        return universal_augment(self.manager, results)


@resources.register('dsql-stream')
class DsqlStream(ChildResourceManager):
    """Amazon Aurora DSQL Stream.

    :example:

    .. code-block:: yaml

        policies:
          - name: dsql-stream-failed
            resource: aws.dsql-stream
            filters:
              - status: FAILED
    """

    class resource_type(TypeInfo):
        service = 'dsql'
        enum_spec = ('list_streams', 'streams', None)
        parent_spec = ('dsql-cluster', 'clusterIdentifier', None)
        id = 'streamIdentifier'
        name = 'streamIdentifier'
        arn = 'arn'
        date = 'creationTime'
        permissions_augment = ('dsql:GetStream',)

    retry = staticmethod(dsql_retry)
    source_mapping = {'describe-child': DescribeStream}


DsqlStream.filter_registry.register('marked-for-op', TagActionFilter)


@DsqlStream.action_registry.register('tag')
class TagDsqlStream(Tag):
    permissions = ('dsql:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {t['Key']: t['Value'] for t in new_tags}
        for r in resources:
            client.tag_resource(resourceArn=r['arn'], tags=tags)


@DsqlStream.action_registry.register('remove-tag')
class RemoveTagDsqlStream(RemoveTag):
    permissions = ('dsql:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            client.untag_resource(resourceArn=r['arn'], tagKeys=tag_keys)


DsqlStream.action_registry.register('mark-for-op', TagDelayedAction)


@DsqlStream.action_registry.register('delete')
class DeleteDsqlStream(BaseAction):
    """Delete a DSQL stream.

    :example:

    .. code-block:: yaml

        policies:
          - name: dsql-stream-delete-failed
            resource: aws.dsql-stream
            filters:
              - status: FAILED
            actions:
              - delete
    """
    schema = type_schema('delete')
    permissions = ('dsql:DeleteStream',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dsql')
        for r in resources:
            try:
                self.manager.retry(
                    client.delete_stream,
                    clusterIdentifier=r['clusterIdentifier'],
                    streamIdentifier=r['streamIdentifier'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    continue
                raise
