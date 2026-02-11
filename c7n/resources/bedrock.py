# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema, QueryParser
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter


class FoundationModelQueryParser(QueryParser):
    QuerySchema = {
        'byProvider': str,
        'byCustomizationType': ('FINE_TUNING', 'CONTINUED_PRE_TRAINING'),
        'byOutputModality': ('TEXT', 'IMAGE', 'EMBEDDING'),
        'byInferenceType': ('ON_DEMAND', 'PROVISIONED'),
    }
    multi_value = False
    type_name = 'Bedrock Foundation Model'


@resources.register('bedrock-foundation-model')
class BedrockFoundationModel(QueryResourceManager):
    """AWS Bedrock Foundation Model

    Foundation models are AWS-managed base models available through Bedrock.
    This resource is read-only (no delete/tag actions) as these are catalog
    items managed by AWS.

    Use the ``query`` parameter for server-side filtering to reduce API response size.

    :example:

    Find all Anthropic models using server-side filtering:

    .. code-block:: yaml

        policies:
          - name: anthropic-models
            resource: aws.bedrock-foundation-model
            query:
              - byProvider: Anthropic
              - byInferenceType: ON_DEMAND

    :example:

    Find active models with client-side filtering:

    .. code-block:: yaml

        policies:
          - name: active-text-models
            resource: aws.bedrock-foundation-model
            filters:
              - type: value
                key: modelLifecycle.status
                value: ACTIVE
              - type: value
                key: outputModalities
                value: TEXT
                op: contains
    """
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_foundation_models', 'modelSummaries', None)
        id = 'modelId'
        arn = 'modelArn'
        name = 'modelName'
        permission_prefix = 'bedrock'

    def resources(self, query=None):
        query = query or {}
        queries = FoundationModelQueryParser.parse(self.data.get('query', []))
        for q in queries:
            query.update(q)
        return super().resources(query=query)


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
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in tags]
            return r
        resources = super().augment(resources)
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
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in tags]
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


@resources.register('bedrock-customization-job')
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
            resource: aws.bedrock-customization-job
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
              resource: aws.bedrock-customization-job
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
              resource: aws.bedrock-customization-job
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
              resource: aws.bedrock-customization-job
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


@resources.register('bedrock-agent')
class BedrockAgent(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock-agent'
        enum_spec = ('list_agents', 'agentSummaries[]', None)
        detail_spec = (
            'get_agent', 'agentId', 'agentId', 'agent')
        name = "agentName"
        id = "agentId"
        arn = "agentArn"
        permission_prefix = 'bedrock'

    def augment(self, resources):
        client = local_session(self.session_factory).client('bedrock-agent')

        def _augment(r):
            tags = self.retry(client.list_tags_for_resource,
                resourceArn=r['agentArn'])['tags']
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]
            r.pop('promptOverrideConfiguration', None)
            return r
        resources = super().augment(resources)
        return list(map(_augment, resources))


@BedrockAgent.filter_registry.register('kms-key')
class BedrockAgentKmsFilter(KmsRelatedFilter):
    """

    Filter bedrock agents by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-agent-kms-key-filter
            resource: aws.bedrock-agent
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/bedrock

    """
    RelatedIdsExpression = 'customerEncryptionKeyArn'


@BedrockAgent.action_registry.register('tag')
class TagBedrockAgent(Tag):
    """Create tags on bedrock agent

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-agent-tag
              resource: aws.bedrock-agent
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
            client.tag_resource(resourceArn=r["agentArn"], tags=tags)


@BedrockAgent.action_registry.register('remove-tag')
class RemoveTagBedrockAgent(RemoveTag):
    """Remove tags from a bedrock agent
    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-agent-untag
              resource: aws.bedrock-agent
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceArn=r['agentArn'], tagKeys=tags)


BedrockAgent.filter_registry.register('marked-for-op', TagActionFilter)


@BedrockAgent.action_registry.register('mark-for-op')
class MarkBedrockAgentForOp(TagDelayedAction):
    """Mark bedrock agent for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-agent-tag-mark
            resource: aws.bedrock-agent
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@BedrockAgent.action_registry.register('delete')
class DeleteBedrockAgentBase(BaseAction):
    """Delete a bedrock agent

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-agent-delete
            resource: aws.bedrock-agent
            actions:
              - type: delete
                skipResourceInUseCheck: false
    """
    schema = type_schema('delete', **{'skipResourceInUseCheck': {'type': 'boolean'}})
    permissions = ('bedrock:DeleteAgent',)

    def process(self, resources):
        skipResourceInUseCheck = self.data.get('skipResourceInUseCheck', False)
        client = local_session(self.manager.session_factory).client('bedrock-agent')
        for r in resources:
            try:
                client.delete_agent(
                    agentId=r['agentId'],
                    skipResourceInUseCheck=skipResourceInUseCheck
                )
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
    """Mark knowledge bases for future actions

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
