# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction


@resources.register('bedrock-custom-model')
class BedrockCustomModel(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_custom_models', 'modelSummaries[]', None)
        detail_spec = (
            'get_custom_model', 'modelIdentifier', 'modelArn', None)
        name = "modelName"
        id = arn = "modelArn"
        permission_prefix = 'bedrock'

    def augment(self, resources):
        client = local_session(self.session_factory).client('bedrock')

        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceARN=r['modelArn'])['tags']
            r['Tags'] = [{'Key': t['key'], 'Value':t['value']} for t in tags]
            return r
        resources = super(BedrockCustomModel, self).augment(resources)
        return list(map(_augment, resources))


@BedrockCustomModel.action_registry.register('tag')
class TagBedrockCustomModel(Tag):
    """Create tags on Bedrock custom models

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-custom-models-tag
              resource: aws.bedrock-custom-model
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('bedrock:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': item['Key'], 'value': item['Value']} for item in new_tags]
        for r in resources:
            client.tag_resource(resourceARN=r["modelArn"], tags=tags)


@BedrockCustomModel.action_registry.register('remove-tag')
class RemoveTagBedrockCustomModel(RemoveTag):
    """Remove tags from a bedrock custom model
    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-model-remove-tag
              resource: aws.bedrock-custom-model
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceARN=r['modelArn'], tagKeys=tags)


BedrockCustomModel.filter_registry.register('marked-for-op', TagActionFilter)
@BedrockCustomModel.action_registry.register('mark-for-op')
class MarkBedrockCustomModelForOp(TagDelayedAction):
    """Mark custom models for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: custom-model-tag-mark
            resource: aws.bedrock-custom-model
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@BedrockCustomModel.action_registry.register('delete')
class DeleteBedrockCustomModel(BaseAction):
    """Delete a bedrock custom model

    :example:

    .. code-block:: yaml

        policies:
          - name: custom-model-delete
            resource: aws.bedrock-custom-model
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('bedrock:DeleteCustomModel',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')
        for r in resources:
            try:
              client.delete_custom_model(modelIdentifier=r['modelArn'])
            except client.exceptions.ResourceNotFoundException:
              continue


@resources.register('bedrock-knowledge-base')
class BedrockKnowledgeBase(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock-agent'
        enum_spec = ('list_knowledge_bases', 'knowledgeBaseSummaries', None)
        detail_spec = (
            'get_knowledge_base', 'knowledgeBaseId', 'knowledgeBaseId', "knowledgeBase")
        name = "name"
        id = "knowledgeBaseId"
        arn = "knowledgeBaseArn"
        permission_prefix = 'bedrock'

    def augment(self, resources):
        client = local_session(self.session_factory).client('bedrock-agent')
        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceArn=r['knowledgeBaseArn'])['tags']
            r['Tags'] = [{'Key': key, 'Value': value} for key, value in tags.items()]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))


@BedrockKnowledgeBase.action_registry.register('tag')
class TagBedrockKnowledgeBase(Tag):
    """Create tags on bedrock knowledge bases

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-knowledge-base-tag
              resource: aws.bedrock-knowledge-base
              actions:
                - type: tag
                  key: test
                  value: test-tag
    """
    permissions = ('bedrock:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {}
        for t in new_tags:
            tags[t['Key']] = t['Value']
        for r in resources:
            client.tag_resource(resourceArn=r["knowledgeBaseArn"], tags=tags)


@BedrockKnowledgeBase.action_registry.register('remove-tag')
class RemoveTagBedrockKnowledgeBase(RemoveTag):
    """Remove tags from a bedrock knowledge base
    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-knowledge-base-untag
              resource: aws.bedrock-knowledge-base
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceArn=r['knowledgeBaseArn'], tagKeys=tags)


BedrockKnowledgeBase.filter_registry.register('marked-for-op', TagActionFilter)
@BedrockKnowledgeBase.action_registry.register('mark-for-op')
class MarkBedrockKnowledgeBaseForOp(TagDelayedAction):
    """Mark custom models for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: knowledge-base-tag-mark
            resource: aws.bedrock-knowledge-base
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@BedrockKnowledgeBase.action_registry.register('delete')
class DeleteBedrockKnowledgeBase(BaseAction):
    """Delete a bedrock knowledge base

    :example:

    .. code-block:: yaml

        policies:
          - name: knowledge-base-delete
            resource: aws.bedrock-knowledge-base
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('bedrock:DeleteKnowledgeBase',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock-agent')
        for r in resources:
            try:
              client.delete_knowledge_base(knowledgeBaseId=r['knowledgeBaseId'])
            except client.exceptions.ResourceNotFoundException:
              continue
