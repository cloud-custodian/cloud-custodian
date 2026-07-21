# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, DescribeWithResourceTags
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment
from c7n.utils import local_session, type_schema, QueryParser
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import MetricsFilter
from c7n.resources.aws import shape_schema, shape_validate, Arn


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
        name = 'jobName'
        id = arn = 'jobArn'
        arn_type = 'model-invocation-job'
        permission_prefix = 'bedrock'
        universal_taggable = object()
        permissions_augment = ("bedrock:ListTagsForResource",)

    augment = universal_augment


@BedrockModelInvocationJob.action_registry.register('stop')
class StopModelInvocationJob(BaseAction):
    """Stop Bedrock model invocation job

    :example:

    .. code-block:: yaml

        policies:
            - name: bedrock-stop-untagged-jobs
              resource: aws.bedrock-model-invocation-job
              filters:
                - 'tag:Owner': absent
                - type: value
                  key: status
                  op: in
                  value: [Submitted, Validating, Scheduled, InProgress]
              actions:
                - type: stop
    """
    schema = type_schema('stop')
    permissions = ('bedrock:StopModelInvocationJob',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')
        for r in resources:
            try:
                client.stop_model_invocation_job(jobIdentifier=r['jobArn'])
            except (client.exceptions.ResourceNotFoundException,
                    client.exceptions.ConflictException) as e:
                self.log.warning('%s', e)


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
        metrics_namespace = "AWS/Bedrock/Agents"

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


@BedrockAgent.filter_registry.register('metrics')
class AgentMetrics(MetricsFilter):
    """Cloudwatch metrics for Bedrock Agents.

    Dataplane metrics for a Bedrock Agent, have a number of caveats.

    They are only defined against a tuple of (OperationId, ModelId, AliasId).

    As such to filter them against an Agent, we query metrics against every
    Alias for each agent.

    Note an OperationId must be supplied via dimension parameter, or a default
    of InvokeAgent will be used.
    """

    def validate(self):
        # operationid must be supplied, of utility with metrics are InvokeAgent
        # and InvokeInlineAgent.
        if not self.data.get('dimensions', {}).get("Operation"):
            self.data.setdefault('dimensions', {})['Operation'] = "InvokeAgent"

    def get_dimensions(self, r):
        # Operation is injected by validate as a user dim, if not user supplied.
        return [
            {'Name': 'AgentAliasArn',
             'Value': f"{r['parent']['arnAliasBase']}/{r['agentAliasId']}"
             },
            {'Name': 'ModelId',
             'Value': r['parent']['modelId']}
        ]

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('bedrock-agent')

        # we do some fancy footwork :-) for the rest of this metrics filter.
        #
        # we switch resources from agents to their set of aliases, if any alias matches
        # we return back the agent with annotations of the matched alias ids.
        # Effectively we create a child resource set and return back the parent on any
        # child matching.

        parents = {r['agentId']: r for r in resources}
        children = []

        for p in parents.values():
            p_arn = Arn.parse(p['agentArn'])
            if 'foundationModel' not in p:
                # We can't build a valid set of dimensions for agent metrics
                # without a model ID.
                continue
            parent_info = {
                'agentId': p['agentId'],
                'arnAliasBase': (f"arn:{p_arn.partition}:bedrock:"
                                 f"{p_arn.region}:{p_arn.account_id}"
                                 f":agent-alias/{p_arn.resource}"),
                'modelId': p['foundationModel']
            }
            child_count = 0
            paginator = client.get_paginator('list_agent_aliases')
            results = paginator.paginate(agentId=p['agentId'])

            for alias in results.build_full_result().get('agentAliasSummaries', []):
                alias['parent'] = parent_info
                children.append(alias)
                child_count += 1
            # seems the only way to determine at a parent level
            # if metrics filer holds true across all children.
            p['c7n:aliasCount'] = child_count

        matched_children = super().process(children)

        matched_parents = set()
        for c in matched_children:
            p = parents[c['parent']['agentId']]
            p.setdefault('c7n:matchedAliases', []).append(
                {'id': c['agentAliasId'], 'name': c['agentAliasName']}
            )
            matched_parents.add(p['agentId'])
        return [parents[pid] for pid in matched_parents]


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
        enum_spec = ('list_inference_profiles', 'inferenceProfileSummaries[]',
            {'typeEquals': 'APPLICATION'})
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


@BedrockApplicationInferenceProfile.filter_registry.register('metrics')
class InferenceProfileMetrics(MetricsFilter):
    def get_dimensions(self, resource):
        return [{'Name': 'ModelId', 'Value': resource['inferenceProfileId']}]


@resources.register('bedrock-provisioned-throughput')
class BedrockProvisionedThroughput(QueryResourceManager):
    """AWS Bedrock Provisioned Throughput

    :example:

    .. code-block:: yaml

        policies:
          - name: bedrock-provisioned-throughput-zero-invocations
            resource: aws.bedrock-provisioned-throughput
            filters:
              - type: value
                key: status
                value: InService
              - type: metrics
                namespace: AWS/Bedrock
                name: Invocations
                statistics: Sum
                days: 14
                period: 86400
                op: eq
                value: 0
                missing-value: 0
    """
    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_provisioned_model_throughputs',
                     'provisionedModelSummaries', None)
        name = 'provisionedModelName'
        id = arn = 'provisionedModelArn'
        arn_type = 'provisioned-model-throughput'
        permission_prefix = 'bedrock'
        universal_taggable = object()
        permissions_augment = ("bedrock:ListTagsForResource",)

    augment = universal_augment


@BedrockProvisionedThroughput.filter_registry.register('metrics')
class ProvisionedThroughputMetrics(MetricsFilter):
    def get_dimensions(self, resource):
        return [{'Name': 'ModelId', 'Value': resource['provisionedModelArn']}]


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
        config_type = cfn_type = 'AWS::Bedrock::Guardrail'

    source_mapping = {'describe': DescribeWithResourceTags}


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
    shape = 'UpdateGuardrailRequest'
    schema = type_schema(
        'update',
        **shape_schema('bedrock', 'UpdateGuardrailRequest'),
    )
    permissions = ('bedrock:UpdateGuardrail',)
    # Keys required by the API, but can default to existing resource values
    required_keys = {
        'name',
        'guardrailIdentifier',
        'blockedInputMessaging',
        'blockedOutputsMessaging',
    }

    def validate(self):
        attrs = {k: 'validate' for k in self.required_keys}
        attrs.update({k: v for k, v in self.data.items() if k != 'type'})
        return shape_validate(attrs, self.shape, self.manager.resource_type.service)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('bedrock')

        # Build update payload from action data (exclude 'type')
        patch = {k: v for k, v in self.data.items() if k != 'type'}

        for r in resources:
            params = {'guardrailIdentifier': r.get('arn'), **patch}

            # API requires certain fields; if they are not provided in the
            # patch, reuse existing values from the resource
            params.update({k: r.get(k) for k in self.required_keys if k not in params})

            try:
                client.update_guardrail(**params)
            except client.exceptions.ResourceNotFoundException:
                continue
