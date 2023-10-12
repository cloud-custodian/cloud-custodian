# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction


@resources.register('opensearch-serverless')
class OpensearchServerless(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'opensearchserverless'
        arn_type = 'arn'
        enum_spec = ('list_collections', 'collectionSummaries[]', None)
        name = "name"
        id = "id"
        universal_taggable = True
        cfn_type = 'AWS::OpenSearchServerless::Collection'
        arn = "arn"
        permission_prefix = 'aoss'

    def augment(self, resources):
        client = local_session(self.session_factory).client('opensearchserverless')
        arn_resources = []
        for r in resources:
            tags = client.list_tags_for_resource(resourceArn=r['arn'])
            r['Tags'] = [{'Key': tag['key'], 'Value': tag['value']} for tag in tags.get('tags', [])]
            arn_resources.append(r)
        return arn_resources


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

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('opensearchserverless')
        for r in resources:
            try:
              client.delete_collection(id=r['id'])
            except client.exceptions.ResourceNotFoundException:
              continue
