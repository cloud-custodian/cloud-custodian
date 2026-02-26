# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment
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


@resources.register('bedrock-model-invocation-job')
class BedrockModelInvocationJob(QueryResourceManager):
    """
    Resource to list batch model invocation jobs.

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-model-invocation-job-inprogress
            resource: aws.bedrock-model-invocation-job
            filters:
              - type: value
                key: status
                value: InProgress
    """

    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_model_invocation_jobs', 'invocationJobSummaries[]', None)
        detail_spec = ('get_model_invocation_job', 'jobIdentifier', 'jobArn', None)
        name = 'jobName'
        id = arn = 'jobArn'
        permission_prefix = 'bedrock'


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


@resources.register('bedrock-inference-profile')
class BedrockApplicationInferenceProfile(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_inference_profiles', 'inferenceProfileSummaries[]', {
            'typeEquals': 'APPLICATION'})
        name = "inferenceProfileName"
        id = arn = "inferenceProfileArn"
        arn_type = "application-inference-profile"
        permission_prefix = 'bedrock'
        universal_taggable = object()
        permissions_augment = ("bedrock:ListTagsForResource",)

    augment = universal_augment


@BedrockApplicationInferenceProfile.action_registry.register('delete')
class DeleteBedrockInferenceProfile(BaseAction):
    """Delete an application inference profile

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-inference-profile
            resource: aws.bedrock-inference-profile
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('bedrock:DeleteInferenceProfile',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')
        for r in resources:
            try:
                client.delete_inference_profile(
                    inferenceProfileIdentifier=r['inferenceProfileArn']
                )
            except client.exceptions.ResourceNotFoundException:
                continue
            except client.exceptions.ConflictException as e:
                self.log.warning(
                    f"Unable to delete inference profile {r['inferenceProfileArn']}: {e}",
                )
                continue


@resources.register('bedrock-guardrail')
class BedrockGuardrail(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_guardrails', 'guardrails[]', {})
        detail_spec = ('get_guardrail', 'guardrailIdentifier', 'id', None)
        name = "name"
        id = "id"
        arn = "arn"
        permission_prefix = 'bedrock'
        universal_taggable = object()
        permissions_augment = ("bedrock:ListTagsForResource",)

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self, resources)


@BedrockGuardrail.action_registry.register('update')
class UpdateGuardrail(BaseAction):
    """Update a Bedrock Guardrail using the `update_guardrail` API.

    The action accepts top-level keys (for example `wordPolicyConfig`) which
    will be merged into the update payload.

    Example policy:

    .. code-block:: yaml

        policies:
          - name: update-guardrail-example
            resource: bedrock-guardrail
            filters:
              - type: value
                key: wordPolicy
                value: absent
            actions:
              - type: update
                wordPolicyConfig:
                  wordsConfig:
                    - text: HATE
                      inputAction: BLOCK
                      outputAction: NONE
                      inputEnabled: true
                      outputEnabled: false
                  managedWordListsConfig:
                    - type: PROFANITY
                      inputAction: BLOCK
                      outputAction: NONE
                      inputEnabled: true
                      outputEnabled: false
    """

    schema = type_schema(
        'update',
        name={'type': 'string'},
        description={'type': 'string'},
        topicPolicyConfig={'type': 'object'},
        contentPolicyConfig={'type': 'object'},
        wordPolicyConfig={'type': 'object'},
        sensitiveInformationPolicyConfig={'type': 'object'},
        contextualGroundingPolicyConfig={'type': 'object'},
        automatedReasoningPolicyConfig={'type': 'object'},
        crossRegionConfig={'type': 'object'},
        blockedInputMessaging={'type': 'string'},
        blockedOutputsMessaging={'type': 'string'},
        kmsKeyId={'type': 'string'},
    )
    permissions = ('bedrock:UpdateGuardrail',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')

        # Build update payload from action data (exclude 'type')
        action_data = dict(self.data or {})
        patch = {}
        for k, v in list(action_data.items()):
            if k != 'type':
                patch[k] = v

        for r in resources:
            guardrail_id = r.get('arn')

            params = {'guardrailIdentifier': guardrail_id}

            # API requires certain fields; if they are not provided in the
            # patch, fetch the current guardrail and reuse its values to
            # avoid ParamValidationError (e.g. name, messaging fields).
            required_fallbacks = ('name', 'blockedInputMessaging', 'blockedOutputsMessaging')
            missing = [k for k in required_fallbacks if k not in patch]
            if missing:
                try:
                    current = (
                        client.get_guardrail(
                            guardrailIdentifier=guardrail_id
                        )
                        .get('guardrail', {})
                    )
                except client.exceptions.ResourceNotFoundException:
                    continue
                # populate missing keys from current guardrail
                for k in missing:
                    # Prefer current server value, then resource value.
                    val = None
                    if current.get(k):
                        val = current.get(k)
                    elif r.get(k):
                        val = r.get(k)
                    if val:
                        patch[k] = val
                    else:
                        # We cannot supply an empty value because botocore
                        # will reject it. Surface a clear error to the
                        # user instead of sending an invalid payload.
                        raise ValueError(
                            (
                                "Unable to determine required field '%s' for guardrail %s; "
                                "please include it in the action payload or ensure the resource "
                                "has it."
                            )
                            % (k, guardrail_id)
                        )

            params.update(patch)

            try:
                client.update_guardrail(**params)
            except client.exceptions.ResourceNotFoundException:
                continue


BedrockGuardrail.filter_registry.register('marked-for-op', TagActionFilter)


@BedrockGuardrail.action_registry.register('mark-for-op')
class MarkBedrockGuardrailForOp(TagDelayedAction):
    """Mark guardrail for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: guardrail-tag-mark
            resource: bedrock-guardrail
            filters:
              - "tag:update": present
            actions:
              - type: mark-for-op
                op: update
                days: 1
    """


@BedrockGuardrail.action_registry.register('tag')
class TagBedrockGuardrail(Tag):
    """Create tags on Bedrock guardrails

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-guardrail-tag
            resource: bedrock-guardrail
            actions:
              - type: tag
                key: NewTag
                value: NewValue
    """
    permissions = ('bedrock:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': item['Key'], 'value': item['Value']} for item in new_tags]
        for r in resources:
            client.tag_resource(resourceARN=r['arn'], tags=tags)


@BedrockGuardrail.action_registry.register('remove-tag')
class RemoveTagBedrockGuardrail(RemoveTag):
    """Remove tags from a bedrock guardrail

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-guardrail-untag
            resource: bedrock-guardrail
            actions:
              - type: remove-tag
                tags: ["tag-key"]
    """
    permissions = ('bedrock:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceARN=r['arn'], tagKeys=tags)
