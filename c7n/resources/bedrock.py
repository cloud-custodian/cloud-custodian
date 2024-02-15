# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter


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


@BedrockCustomModel.filter_registry.register('kms-key')
class BedrockCustomModelKmsFilter(KmsRelatedFilter):
    """

    Filter bedrock custom models by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-custom-model-kms-key-filter
            resource: aws.bedrock-custom-model
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/bedrock

    """
    RelatedIdsExpression = 'modelKmsKeyArn'


class DescribeBedrockCustomizationJob(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')

        def _augment(r):
            tags = client.list_tags_for_resource(resourceARN=r['jobArn'])['tags']
            r['Tags'] = [{'Key': t['key'], 'Value':t['value']} for t in tags]
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('bedrock')
        resources = []
        for rid in resource_ids:
            r = client.get_model_customization_job(jobIdentifier=rid)
            if r.get('status') == 'InProgress':
                resources.append(r)
        return resources


@resources.register('model-customization-job')
class BedrockModelCustomizationJob(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_model_customization_jobs', 'modelCustomizationJobSummaries[]', {
            'statusEquals': 'InProgress'})
        detail_spec = (
            'get_model_customization_job', 'jobIdentifier', 'jobName', None)
        name = "jobName"
        id = arn = "jobArn"
        permission_prefix = 'bedrock'

    source_mapping = {
        'describe': DescribeBedrockCustomizationJob
    }


@BedrockModelCustomizationJob.filter_registry.register('kms-key')
class BedrockCustomizationJobsKmsFilter(KmsRelatedFilter):
    """

    Filter bedrock customization jobs by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-customization-job-kms-key-filter
            resource: aws.model-customization-job
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/bedrock

    """
    RelatedIdsExpression = 'outputModelKmsKeyArn'


@BedrockModelCustomizationJob.action_registry.register('tag')
class TagModelCustomizationJob(Tag):
    """Create tags on Bedrock model customization jobs

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-model-customization-job-tag
              resource: aws.model-customization-job
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('bedrock:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': item['Key'], 'value': item['Value']} for item in new_tags]
        for r in resources:
            client.tag_resource(resourceARN=r["jobArn"], tags=tags)


@BedrockModelCustomizationJob.action_registry.register('remove-tag')
class RemoveTagModelCustomizationJob(RemoveTag):
    """Remove tags from Bedrock model customization jobs

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-model-customization-job-remove-tag
              resource: aws.model-customization-job
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceARN=r['jobArn'], tagKeys=tags)


@BedrockModelCustomizationJob.action_registry.register('stop')
class StopCustomizationJob(BaseAction):
    """Stop model customization job

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-model-customization-untagged-stop
              resource: aws.model-customization-job
              filters:
                - tag:Owner: absent
              actions:
                - type: stop

    """
    schema = type_schema('stop')
    permissions = ('bedrock:StopModelCustomizationJob',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')
        for r in resources:
            client.stop_model_customization_job(jobIdentifier=r['jobArn'])
