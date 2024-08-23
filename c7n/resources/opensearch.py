# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter


@resources.register('opensearch-serverless')
class OpensearchServerless(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'opensearchserverless'
        arn_type = 'arn'
        enum_spec = ('list_collections', 'collectionSummaries[]', None)
        batch_detail_spec = (
            'batch_get_collection', 'ids', 'id',
            'collectionDetails', None)
        name = "name"
        id = "id"
        cfn_type = 'AWS::OpenSearchServerless::Collection'
        arn = "arn"
        permission_prefix = 'aoss'
        permissions_augment = ("aoss:ListTagsForResource",)

    def augment(self, resources):
        client = local_session(self.session_factory).client('opensearchserverless')

        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceArn=r['arn'])['tags']
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in tags]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))


@OpensearchServerless.filter_registry.register('kms-key')
class OpensearchServerlessKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'kmsKeyArn'


@OpensearchServerless.action_registry.register('tag')
class TagOpensearchServerlessResource(Tag):
    """Create tags on an OpenSearch Serverless resource

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-opensearch-serverless
              resource: opensearch-serverless
              actions:
                - type: tag
                  key: test-key
                  value: test-value
    """
    permissions = ('aoss:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': item['Key'], 'value': item['Value']} for item in new_tags]
        for r in resources:
            client.tag_resource(resourceArn=r["arn"], tags=tags)


@OpensearchServerless.action_registry.register('remove-tag')
class RemoveTagOpensearchServerlessResource(RemoveTag):
    """Remove tags from an OpenSearch serverless resource

    :example:

    .. code-block:: yaml

        policies:
            - name: remove-tag-opensearch-serverless
              resource: opensearch-serverless
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('aoss:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceArn=r['arn'], tagKeys=tags)


OpensearchServerless.filter_registry.register('marked-for-op', TagActionFilter)


@OpensearchServerless.action_registry.register('mark-for-op')
class MarkOpensearchServerlessForOp(TagDelayedAction):
    """Mark OpenSearch Serverless for deferred action

    :example:

    .. code-block:: yaml

        policies:
          - name: opensearch-serverless-invalid-tag-mark
            resource: opensearch-serverless
            filters:
              - "tag:InvalidTag": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@OpensearchServerless.action_registry.register('delete')
class DeleteOpensearchServerless(BaseAction):
    """Delete an OpenSearch Serverless

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-opensearch-serverless
            resource: opensearch-serverless
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('aoss:DeleteCollection',)
    valid_delete_states = ('ACTIVE', 'FAILED')

    def process(self, resources):
        resources = self.filter_resources(resources, "status", self.valid_delete_states)
        client = local_session(self.manager.session_factory).client('opensearchserverless')
        for r in resources:
            try:
                client.delete_collection(id=r['id'])
            except client.exceptions.ResourceNotFoundException:
                continue


@resources.register('opensearch-injestion')
class OpensearchInjestion(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'osis'
        arn_type = 'pipeline'
        enum_spec = ('list_pipelines', 'Pipelines[]', None)
        detail_spec = ('get_pipeline', 'PipelineName', 'PipelineName', 'Pipeline')
        name = id = "PipelineName"
        cfn_type = 'AWS::OSIS::Pipeline'
        arn = "PipelineArn"
        permission_prefix = 'osis'


@OpensearchInjestion.filter_registry.register('kms-key')
class OpensearchInjestionKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'EncryptionAtRestOptions.KmsKeyArn'


@OpensearchInjestion.action_registry.register('tag')
class TagOpensearchInjestion(Tag):
    """Create tags on an OpenSearch Injestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-opensearch-injestion
              resource: opensearch-injestion
              actions:
                - type: tag
                  key: test-key
                  value: test-value
    """
    permissions = ('osis:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'Key': t['Key'], 'Value': t['Value']} for t in new_tags]
        for r in resources:
            client.tag_resource(Arn=r["PipelineArn"], Tags=tags)


@OpensearchInjestion.action_registry.register('remove-tag')
class RemoveTagOpensearchInjestion(RemoveTag):
    """Remove tags from an OpenSearch Injestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
            - name: remove-tag-opensearch-injestion
              resource: opensearch-injestion
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('osis:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(Arn=r['PipelineArn'], TagKeys=tags)


OpensearchInjestion.filter_registry.register('marked-for-op', TagActionFilter)


@OpensearchInjestion.action_registry.register('mark-for-op')
class MarkOpensearchInjestionForOp(TagDelayedAction):
    """Mark OpenSearch Injestion Pipeline for deferred action

    :example:

    .. code-block:: yaml

        policies:
          - name: opensearch-injestion-invalid-tag-mark
            resource: opensearch-injestion
            filters:
              - "tag:InvalidTag": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@OpensearchInjestion.action_registry.register('delete')
class DeleteOpensearchInjestion(BaseAction):
    """Delete an OpenSearch Injestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-opensearch-injestion
            resource: opensearch-injestion
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('osis:DeletePipeline',)
    valid_delete_states = (
        'ACTIVE', 'CREATE_FAILED', 'UPDATE_FAILED', 'STARTING', 'START_FAILED', 'STOPPING',
        'STOPPED'
    )

    def process(self, resources):
        resources = self.filter_resources(resources, "Status", self.valid_delete_states)
        client = local_session(self.manager.session_factory).client('osis')
        for r in resources:
            try:
                client.delete_pipeline(PipelineName=r['PipelineName'])
            except client.exceptions.ResourceNotFoundException:
                continue


@OpensearchInjestion.action_registry.register('stop')
class StopOpensearchInjestion(BaseAction):
    """Stops an Opensearch Injestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-osis-pipeline
            resource: opensearch-injestion
            filters:
              - PipelineName: c7n-pipeline-1
            actions:
              - stop
    """
    schema = type_schema('stop')
    permissions = ('osis:StopPipeline',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('osis')

        for r in resources:
            try:
                client.stop_pipeline(PipelineName=r['PipelineName'])
            except client.exceptions.ResourceNotFound:
                pass


@OpensearchInjestion.action_registry.register('update')
class UpdateOpenSearchInjestion(BaseAction):
    """Modifies MinUnits, MaxUnits, LogPublishingOptions, BufferOptions, and
    EncryptionAtRestOptions for a given Opensearch Injestion pipeline.

    :example:

    .. code-block:: yaml

            policies:
              - name: update-pipeline
                resource: aws.opensearch-injestion
                actions:
                  - type: update
                    LogPublishingOptions:
                        IsLoggingEnabled: true
                        CloudWatchLogDestination:
                            LogGroup: c7n-log-group
                    BufferOptions:
                        PersistentBufferEnabled: true

    """
    schema = type_schema(
        'update',
        MinUnits={'type': 'integer'},
        MaxUnits={'type': 'integer'},
        LogPublishingOptions={'type': 'object',
            'properties': {
                'IsLoggingEnabled': {'type': 'boolean'},
                'CloudWatchLogDestination': {'type': 'object',
                    'required': ['LogGroup'],
                    'properties': {
                        'LogGroup': {'type': 'string'}
                    }
                }
            }
        },
        BufferOptions={'type': 'object',
            'required': ['PersistentBufferEnabled'],
            'properties': {
                'PersistentBufferEnabled': {'type': 'boolean'}}},
        EncryptionAtRestOptions={'type': 'object',
            'required': ['KmsKeyArn'],
            'properties': {
                'KmsKeyArn': {'type': 'string'}}})
    permissions = ('osis:UpdatePipeline',)

    def process(self, resources):
        params = dict(self.data)
        params.pop("type")
        client = local_session(self.manager.session_factory).client('osis')
        for r in resources:
            try:
                client.update_pipeline(PipelineName=r['PipelineName'], **params)
            except client.exceptions.ResourceNotFoundException:
                continue
