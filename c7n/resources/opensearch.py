# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseAction
from c7n.filters import ValueFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema, yaml_load
from fnmatch import fnmatch
import json


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

@OpensearchServerless.filter_registry.register('cross-account')
class OpensearchServerlessCrossAccountFilter(CrossAccountAccessFilter):
    """
    Filter OpenSearch Ingestion Pipelines by cross-account access
    
    :example:

    .. code-block:: yaml

        policies:
          - name: aoss-cross-account
            resource: opensearch-serverless
            filters:
              - type: cross-account
    """
    policy_attribute = 'c7n:Policy'
    permissions = ('aoss:GetAccessPolicy', 'aoss:ListAccessPolicies')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('opensearchserverless')
        self.get_resource_policies(client, resources) 
        return super().process(resources, event)

    def get_resource_policies(self, client, resources): 
        # Cache 'em policies for the session to avoid repeated scans
        cache_key = 'aoss-data-policies'
        all_policies = self.manager._cache.get(cache_key)
        
        if not all_policies:
            policies = []
            next_token = None
            while True:
                params = {'type': 'data'}
                if next_token:
                    params['nextToken'] = next_token
                
                response = client.list_access_policies(**params)
                
                for p in response.get('accessPolicySummaries', []):
                    detail = self.manager.retry(
                        client.get_access_policy,
                        type='data',
                        name=p['name']
                    )
                    if detail:
                        if isinstance(detail['accessPolicyDetail']['policy'], str):
                            policies.append(json.loads(detail['accessPolicyDetail']['policy']))
                        else:
                            policies.append(detail['accessPolicyDetail']['policy'])
                
                next_token = response.get('nextToken')
                if not next_token:
                    break
            
            all_policies = policies
            try:
                self.manager._cache[cache_key] = all_policies
            except Exception:
                pass
        
        for r in resources:
            if self.policy_attribute in r:
                continue

            matching_rules = []
            for policy in all_policies:
                if isinstance(policy, list):
                    for rule in policy:
                        # Check if this rule applies to the current collection
                        matches_resource = False
                        for pattern in rule.get('Rules', []):
                            for res in pattern.get('Resource', []):
                                if res.startswith('collection/'):
                                    coll_pattern = res.split('/', 1)[1]
                                    if fnmatch(r['name'], coll_pattern):
                                        matches_resource = True
                                        break
                            if matches_resource:
                                break
                        
                        if matches_resource:
                            matching_rules.append(rule)
            
            if matching_rules:
                r[self.policy_attribute] = self.marshal_policy(matching_rules, r['arn'])
            else:
                r[self.policy_attribute] = None

    def marshal_policy(self, rules, resource_arn):
        # Convert AOSS rules list to logical IAM Policy
        iam_policy = {
            "Version": "2012-10-17",
            "Statement": []
        }
        
        for rule in rules:
            statement = {
                "Effect": "Allow",
                "Principal": {"AWS": rule.get('Principal', [])},
                "Action": [],
                "Resource": [resource_arn]
            }
            # handle permissions
            for sub_rule in rule.get('Rules', []):
                statement['Action'].extend(sub_rule.get('Permission', []))
            iam_policy['Statement'].append(statement)
            
        return iam_policy

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


@resources.register('opensearch-ingestion')
class OpensearchIngestion(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'osis'
        arn_type = 'pipeline'
        enum_spec = ('list_pipelines', 'Pipelines[]', None)
        detail_spec = ('get_pipeline', 'PipelineName', 'PipelineName', 'Pipeline')
        name = id = "PipelineName"
        cfn_type = 'AWS::OSIS::Pipeline'
        arn = "PipelineArn"
        permission_prefix = 'osis'


@OpensearchIngestion.filter_registry.register('kms-key')
class OpensearchIngestionKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'EncryptionAtRestOptions.KmsKeyArn'


@OpensearchIngestion.filter_registry.register('pipeline-config')
class OpensearchIngestionPipelineConfigFilter(ValueFilter):
    """Filter OpenSearch Ingestion Pipelines by their PipelineConfiguration.
    Custodian substitutes the pipeline name key in the PipelineConfigurationBody with
    'pipeline' so that its sub-fields can be referenced in the filter.

    :example:

    .. code-block:: yaml

        policies:
          - name: osis-persistent-buffer-disabled
            resource: opensearch-ingestion
            filters:
              - or:
                - type: pipeline-config
                  key: pipeline.source.http
                  value: not-null
                - type: pipeline-config
                  key: pipeline.source.otel
                  value: not-null
              - type: value
                key: BufferOptions.PersistentBufferEnabled
                op: ne
                value: True
    """
    annotation_key = 'c7n:PipelineConfiguration'
    schema = type_schema(
        'pipeline-config',
        rinherit=ValueFilter.schema,
    )
    permissions = ('osis:ListPipelines',)
    pipeline_name_key_substitute = "pipeline"

    def substitute_pipeline_name_key(self, pipeline_config):
        for key in list(pipeline_config.keys()):
            if isinstance(pipeline_config[key], dict) and "source" in pipeline_config[key].keys():
                pipeline_config[self.pipeline_name_key_substitute] = pipeline_config.pop(key)
                continue

    def augment(self, r):
        if self.annotation_key not in r:
            r[self.annotation_key] = yaml_load(r.get('PipelineConfigurationBody', '{}'))
            self.substitute_pipeline_name_key(r[self.annotation_key])

    def process(self, resources, event=None):
        matched = []
        for r in resources:
            self.augment(r)
            if self.match(r[self.annotation_key]):
                matched.append(r)
        return matched

@OpensearchIngestion.filter_registry.register('cross-account')
class CrossAccountFilter(CrossAccountAccessFilter):
    """
    Filter OpenSearch Ingestion Pipelines by cross-account access
    
    :example:

    .. code-block:: yaml

        policies:
          - name: osis-cross-account
            resource: opensearch-ingestion
            filters:
              - type: cross-account
    """
    policy_attribute = 'c7n:Policy'
    permissions = ('osis:ListPipelines',)
    
    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('osis')
        iam_client = local_session(self.manager.session_factory).client('iam')
        
        for r in resources:
            if self.policy_attribute in r:
                continue
            
            statements = []
            
            # Pipeline Resource Policy cross account check
            try:
                res_policy = self.manager.retry(
                    client.get_resource_policy,
                    ResourceArn=r['PipelineArn'],
                    ignore_err_codes=('ResourceNotFoundException',))
                if res_policy and res_policy.get('Policy'):
                    p = json.loads(res_policy['Policy'])
                    statements.extend(p.get('Statement', []))
            except Exception:
                pass
                
            # Role Trust Policy cross account check
            role_arn = r.get('PipelineRoleArn')
            if role_arn:
                cache_key = 'iam-role-{}'.format(role_arn)
                role = self.manager._cache.get(cache_key)
                if not role:
                    try:
                        role_name = role_arn.split('/')[-1]
                        role = iam_client.get_role(RoleName=role_name)['Role']
                        try:
                            self.manager._cache[cache_key] = role
                        except Exception:
                            pass
                    except Exception:
                        pass
                
                if role and role.get('AssumeRolePolicyDocument'):
                    trust_policy = role['AssumeRolePolicyDocument']
                    if isinstance(trust_policy, str):
                        if trust_policy.startswith('%'):
                            from urllib.parse import unquote
                            trust_policy = unquote(trust_policy)
                        trust_policy = json.loads(trust_policy)
                    statements.extend(trust_policy.get('Statement', []))
            
            if statements:
                r[self.policy_attribute] = {
                    "Version": "2012-10-17",
                    "Statement": statements
                }
            else:
                r[self.policy_attribute] = None
                
        return super().process(resources, event)



@OpensearchIngestion.action_registry.register('tag')
class TagOpensearchIngestion(Tag):
    """Create tags on an OpenSearch Ingestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-opensearch-ingestion
              resource: opensearch-ingestion
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


@OpensearchIngestion.action_registry.register('remove-tag')
class RemoveTagOpensearchIngestion(RemoveTag):
    """Remove tags from an OpenSearch Ingestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
            - name: remove-tag-opensearch-ingestion
              resource: opensearch-ingestion
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('osis:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(Arn=r['PipelineArn'], TagKeys=tags)


OpensearchIngestion.filter_registry.register('marked-for-op', TagActionFilter)


@OpensearchIngestion.action_registry.register('mark-for-op')
class MarkOpensearchIngestionForOp(TagDelayedAction):
    """Mark OpenSearch Ingestion Pipeline for deferred action

    :example:

    .. code-block:: yaml

        policies:
          - name: opensearch-ingestion-invalid-tag-mark
            resource: opensearch-ingestion
            filters:
              - "tag:InvalidTag": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@OpensearchIngestion.action_registry.register('delete')
class DeleteOpensearchIngestion(BaseAction):
    """Delete an OpenSearch Ingestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-opensearch-ingestion
            resource: opensearch-ingestion
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


@OpensearchIngestion.action_registry.register('stop')
class StopOpensearchIngestion(BaseAction):
    """Stops an Opensearch Ingestion Pipeline

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-osis-pipeline
            resource: opensearch-ingestion
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


@OpensearchIngestion.action_registry.register('update')
class UpdateOpenSearchIngestion(BaseAction):
    """Modifies MinUnits, MaxUnits, LogPublishingOptions, BufferOptions, and
    EncryptionAtRestOptions for a given Opensearch Ingestion pipeline.

    :example:

    .. code-block:: yaml

            policies:
              - name: update-pipeline
                resource: aws.opensearch-ingestion
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
