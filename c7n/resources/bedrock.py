# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
from urllib.parse import urlsplit

from c7n.manager import resources
from c7n.exceptions import PolicyValidationError
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, DescribeWithResourceTags
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment
from c7n.utils import local_session, type_schema, QueryParser
from c7n.actions import BaseAction
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import MetricsFilter, ValueFilter
from c7n.resources.aws import shape_schema, shape_validate, Arn
from c7n.resources.s3 import BucketAssembly, S3_AUGMENT_TABLE


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
    """Filter inference profiles by published or combined token usage.

    ``c7n:TotalTokenCount`` is a Custodian-derived metric that sums Bedrock's
    ``InputTokenCount`` and ``OutputTokenCount`` metrics. Its statistic is
    always ``Sum`` and defaults to that value when omitted.

    A completed daily total can be selected with ``days: 1``, ``period:
    86400``, and ``period-start: start-of-day``. For a single completed
    seven-day aggregate use ``days: 7`` and ``period: 604800``. Using a period
    of 86400 over seven days produces seven datapoints, all of which must meet
    the configured comparison.

    :example:

    Match profiles whose total token consumption for the last completed day
    exceeds 100,000 tokens:

    .. code-block:: yaml

        policies:
          - name: bedrock-daily-token-usage
            resource: aws.bedrock-inference-profile
            filters:
              - type: metrics
                name: c7n:TotalTokenCount
                days: 1
                period: 86400
                period-start: start-of-day
                value: 100000
                op: greater-than

    :example:

    Match a single completed seven-day aggregate above 700,000 tokens:

    .. code-block:: yaml

        policies:
          - name: bedrock-weekly-token-usage
            resource: aws.bedrock-inference-profile
            filters:
              - type: metrics
                name: c7n:TotalTokenCount
                days: 7
                period: 604800
                period-start: start-of-day
                value: 700000
                op: greater-than
    """
    TOTAL_TOKEN_COUNT = 'c7n:TotalTokenCount'

    def validate(self):
        if (self.data['name'] == self.TOTAL_TOKEN_COUNT and
                self.data.get('statistics', 'Sum') != 'Sum'):
            raise PolicyValidationError(
                "metrics filter c7n:TotalTokenCount only supports the Sum statistic")
        return super().validate()

    def process(self, resources, event=None):
        if self.data['name'] == self.TOTAL_TOKEN_COUNT:
            self.data.setdefault('statistics', 'Sum')
        return super().process(resources, event)

    def get_permissions(self):
        if self.data.get('name') == self.TOTAL_TOKEN_COUNT:
            return ('cloudwatch:GetMetricData',)
        return self.permissions

    def get_dimensions(self, resource):
        return [{'Name': 'ModelId', 'Value': resource['inferenceProfileId']}]

    def get_metric_data(self, client, params):
        if self.metric != self.TOTAL_TOKEN_COUNT:
            return super().get_metric_data(client, params)

        metric_stat = {
            'Namespace': params['Namespace'],
            'Dimensions': params['Dimensions'],
        }
        queries = []
        for query_id, metric_name in (
                ('input', 'InputTokenCount'), ('output', 'OutputTokenCount')):
            queries.append({
                'Id': query_id,
                'MetricStat': {
                    'Metric': dict(metric_stat, MetricName=metric_name),
                    'Period': params['Period'],
                    'Stat': 'Sum',
                },
                'ReturnData': False,
            })
        queries.append({
            'Id': 'total',
            'Expression': 'input + output',
            'Label': self.TOTAL_TOKEN_COUNT,
            'ReturnData': True,
        })

        datapoints = []
        request = {
            'MetricDataQueries': queries,
            'StartTime': params['StartTime'],
            'EndTime': params['EndTime'],
        }
        paginator = client.get_paginator('get_metric_data')
        for response in paginator.paginate(**request):
            for result in response.get('MetricDataResults', ()):
                if result['Id'] != 'total':
                    continue
                datapoints.extend({
                    'Timestamp': timestamp,
                    self.statistics: value,
                } for timestamp, value in zip(
                    result.get('Timestamps', ()), result.get('Values', ())))
        return datapoints


@resources.register('bedrock-evaluation-job')
class BedrockEvaluationJob(QueryResourceManager):
    """AWS Bedrock Evaluation Job

    :example:

    Find terminal evaluation jobs with an S3 output location:

    .. code-block:: yaml

        policies:
          - name: bedrock-terminal-evaluation-jobs
            resource: aws.bedrock-evaluation-job
            filters:
              - type: value
                key: status
                op: in
                value: [Completed, Failed, Stopped]
              - type: value
                key: outputDataConfig.s3Uri
                value: present
    """

    class resource_type(TypeInfo):
        service = 'bedrock'
        enum_spec = ('list_evaluation_jobs', 'jobSummaries[]', None)
        detail_spec = ('get_evaluation_job', 'jobIdentifier', 'jobArn', None)
        name = 'jobName'
        id = arn = 'jobArn'
        arn_type = 'evaluation-job'
        permission_prefix = 'bedrock'
        universal_taggable = object()
        permissions_augment = ('bedrock:ListTagsForResource',)

    source_mapping = {'describe': DescribeWithResourceTags}


BEDROCK_OUTPUT_BUCKET_MANDATORY_KEYS = ('Location', 'Tags')
BEDROCK_OUTPUT_ANNOTATION = 'c7n:BedrockEvaluationOutput'


class BedrockOutputBucketAssembly(BucketAssembly):

    def __init__(self, manager):
        super().__init__(manager)
        self.not_found_buckets = set()

    def handle_not_found(self, bucket, method_name, error_code=None):
        if error_code in ('NoSuchBucket', 'NotFound'):
            self.not_found_buckets.add(bucket['Name'])


def parse_bedrock_output_s3_uri(s3_uri):
    """Return a bucket and prefix without decoding the URI path."""
    if not s3_uri:
        return None, None, 'missing-uri'
    if not isinstance(s3_uri, str):
        return None, None, 'invalid-uri'
    try:
        parsed = urlsplit(s3_uri)
        invalid = (parsed.scheme != 's3' or not parsed.netloc or parsed.username or
                   parsed.password or parsed.port is not None or
                   parsed.query or parsed.fragment)
    except ValueError:
        return None, None, 'invalid-uri'
    if invalid:
        return None, None, 'invalid-uri'
    return parsed.netloc, parsed.path.lstrip('/'), None


def get_bedrock_output_artifact_prefix(output_prefix, resource):
    """Return the common prefix under which Bedrock writes a job's artifacts."""
    job_name = resource.get('jobName')
    job_arn = resource.get('jobArn', '')
    job_id = job_arn.rsplit('/', 1)[-1] if '/' in job_arn else None
    if not job_name or not job_id:
        return output_prefix
    parent = output_prefix.rstrip('/')
    return '/'.join(filter(None, (parent, job_name, job_id))) + '/'


def _lifecycle_rule_prefix(rule):
    rule_filter = rule.get('Filter')
    if isinstance(rule_filter, dict):
        if 'Prefix' in rule_filter:
            return rule_filter.get('Prefix') or ''
        rule_and = rule_filter.get('And')
        if isinstance(rule_and, dict) and 'Prefix' in rule_and:
            return rule_and.get('Prefix') or ''
        # A filter containing only constraints still applies at the root.
        return ''
    return rule.get('Prefix') or ''


def _lifecycle_rule_is_constrained(rule):
    rule_filter = rule.get('Filter')
    if not isinstance(rule_filter, dict):
        return False
    constraint_keys = {
        'Tag', 'Tags', 'ObjectSizeGreaterThan', 'ObjectSizeLessThan'}
    if constraint_keys.intersection(rule_filter):
        return True
    rule_and = rule_filter.get('And')
    return isinstance(rule_and, dict) and bool(constraint_keys.intersection(rule_and))


def _lifecycle_expiration_days(rule):
    expiration = rule.get('Expiration')
    days = expiration.get('Days') if isinstance(expiration, dict) else None
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        return days


def _lifecycle_noncurrent_expiration_days(rule):
    expiration = rule.get('NoncurrentVersionExpiration')
    if isinstance(expiration, dict) and expiration.get('NewerNoncurrentVersions') is not None:
        return None
    days = expiration.get('NoncurrentDays') if isinstance(expiration, dict) else None
    if isinstance(days, (int, float)) and not isinstance(days, bool):
        return days


def _bucket_is_versioned(versioning):
    if not isinstance(versioning, dict):
        return False
    return versioning.get('Status') in ('Enabled', 'Suspended')


def get_bedrock_output_lifecycle(lifecycle, output_prefix, versioning=None):
    """Calculate covering lifecycle rules and guaranteed expiration days."""
    rules = lifecycle.get('Rules', []) if isinstance(lifecycle, dict) else []
    matched = []
    current_expiration = []
    noncurrent_expiration = []
    versioned = _bucket_is_versioned(versioning)
    for rule in rules:
        rule_prefix = _lifecycle_rule_prefix(rule)
        if not isinstance(rule_prefix, str) or not output_prefix.startswith(rule_prefix):
            continue
        matched.append(rule)
        if (rule.get('Status') == 'Enabled' and
                not _lifecycle_rule_is_constrained(rule)):
            days = _lifecycle_expiration_days(rule)
            if days is not None:
                current_expiration.append(days)
            days = _lifecycle_noncurrent_expiration_days(rule)
            if days is not None:
                noncurrent_expiration.append(days)
    if not current_expiration:
        return matched, None
    if versioned:
        if not noncurrent_expiration:
            return matched, None
        return matched, min(current_expiration) + min(noncurrent_expiration)
    return matched, min(current_expiration)


@BedrockEvaluationJob.filter_registry.register('output-retention')
class BedrockEvaluationOutputRetention(ValueFilter):
    """Filter evaluation jobs by their S3 output artifact retention."""

    DEFAULT_KEY = '"%s".EffectiveExpirationDays' % BEDROCK_OUTPUT_ANNOTATION

    schema = type_schema(
        'output-retention', rinherit=ValueFilter.schema)
    schema_alias = False

    def __init__(self, data, manager=None):
        data = dict(data)
        data.setdefault('key', self.DEFAULT_KEY)
        super().__init__(data, manager)

    def validate(self):
        key = self.data.get('key', self.DEFAULT_KEY)
        if not key.startswith('"%s".' % BEDROCK_OUTPUT_ANNOTATION):
            raise PolicyValidationError(
                'output-retention key must reference "%s"' %
                BEDROCK_OUTPUT_ANNOTATION)
        return super().validate()

    def get_permissions(self):
        fields = set(BEDROCK_OUTPUT_BUCKET_MANDATORY_KEYS)
        fields.update(('Lifecycle', 'Versioning'))
        return tuple(row[4] for row in S3_AUGMENT_TABLE if row[1] in fields)

    def _augment_buckets(self, bucket_names):
        if not bucket_names:
            return {}
        assembler = BedrockOutputBucketAssembly(self.manager)
        assembler.initialize()
        assembler.augment_fields = set(BEDROCK_OUTPUT_BUCKET_MANDATORY_KEYS)
        assembler.augment_fields.update(('Lifecycle', 'Versioning'))
        buckets = {}
        for name in bucket_names:
            bucket = assembler.assemble({'Name': name})
            if name in assembler.not_found_buckets:
                bucket['c7n:BedrockOutputBucketError'] = 'bucket-not-found'
            buckets[name] = bucket
        return buckets

    def _get_context(
            self, s3_uri, bucket, bucket_name, prefix, artifact_prefix, error):
        context = copy.deepcopy(bucket) if bucket is not None else {}
        if bucket_name is not None:
            context.setdefault('Name', bucket_name)
        output = {
            'S3Uri': s3_uri,
            'Prefix': prefix,
            'ArtifactPrefix': artifact_prefix,
            'PrefixMatchedLifecycleRules': [],
            'Error': error,
        }

        denied = context.get('c7n:DeniedMethods', ())
        if error is None and bucket is not None:
            bucket_error = context.pop('c7n:BedrockOutputBucketError', None)
            if bucket_error:
                output['Error'] = bucket_error
            elif 'get_bucket_lifecycle_configuration' in denied:
                output['Error'] = 'lifecycle-access-denied'
            elif 'get_bucket_versioning' in denied:
                output['Error'] = 'versioning-access-denied'

        if output['Error'] is None:
            matched, effective = get_bedrock_output_lifecycle(
                context.get('Lifecycle'), artifact_prefix, context.get('Versioning'))
            output['PrefixMatchedLifecycleRules'] = matched
            if effective is not None:
                output['EffectiveExpirationDays'] = effective
        context[BEDROCK_OUTPUT_ANNOTATION] = output
        return context

    def process(self, resources, event=None):
        parsed = []
        bucket_names = set()
        for resource in resources:
            s3_uri = resource.get('outputDataConfig', {}).get('s3Uri')
            bucket_name, prefix, error = parse_bedrock_output_s3_uri(s3_uri)
            parsed.append((resource, s3_uri, bucket_name, prefix, error))
            if bucket_name is not None:
                bucket_names.add(bucket_name)

        buckets = self._augment_buckets(sorted(bucket_names))
        results = []
        for resource, s3_uri, bucket_name, prefix, error in parsed:
            artifact_prefix = (
                get_bedrock_output_artifact_prefix(prefix, resource)
                if error is None else prefix)
            context = self._get_context(
                s3_uri, buckets.get(bucket_name), bucket_name, prefix,
                artifact_prefix, error)
            if self.match(context):
                resource['c7n:OutputBucket'] = context
                results.append(resource)
        return results


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
