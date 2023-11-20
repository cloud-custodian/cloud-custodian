# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction


@resources.register('bedrock-custom-models')
class BedrockCustomModels(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_custom_models', 'modelSummaries[]', None)
        detail_spec = (
            'get_custom_model', 'modelIdentifier', 'modelArn', None)
        id = name = "modelName"
        arn = "modelArn"
        permission_prefix = 'bedrock'

    def augment(self, resources):
        client = local_session(self.session_factory).client('bedrock')

        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceARN=r['modelArn'])['tags']
            r['Tags'] = [{'Key': t['key'], 'Value':t['value']} for t in tags]
            return r
        resources = super(BedrockCustomModels, self).augment(resources)
        return list(map(_augment, resources))


@BedrockCustomModels.action_registry.register('tag')
class TagBedrockCustomModel(Tag):
    """Create tags on Bedrock custom models

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-custom-models-tag
              resource: aws.bedrock-custom-models
              actions:
                - type: tag
                  key: test
                  value: value
    """
    permissions = ('bedrock:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': item['Key'], 'value': item['Value']} for item in new_tags]
        for r in resources:
            client.tag_resource(resourceARN=r["modelArn"], tags=tags)


@BedrockCustomModels.action_registry.register('remove-tag')
class RemoveTagBedrockCustomModel(RemoveTag):
    """Remove tags from a bedrock custom model
    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-model-remove-tag
              resource: aws.bedrock-custom-models
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceARN=r['modelArn'], tagKeys=tags)


BedrockCustomModels.filter_registry.register('marked-for-op', TagActionFilter)
@BedrockCustomModels.action_registry.register('mark-for-op')
class MarkOpensearchServerlessForOp(TagDelayedAction):
    """Mark custom models for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: custom-model-tag-mark
            resource: aws.bedrock-custom-models
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@BedrockCustomModels.action_registry.register('delete')
class DeleteBedrockCustomModel(BaseAction):
    """Delete a bedrock custom model

    :example:

    .. code-block:: yaml

        policies:
          - name: custom-model-delete
            resource: aws.bedrock-custom-models
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
