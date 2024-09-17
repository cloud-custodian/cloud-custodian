# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import Tag, RemoveTag, universal_augment
from c7n.utils import type_schema, local_session, dumps, chunks
from c7n.filters.kms import KmsRelatedFilter


class DescribeStepFunction(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


@resources.register('step-machine')
class StepFunction(QueryResourceManager):
    """AWS Step Functions State Machine"""

    class resource_type(TypeInfo):
        service = 'stepfunctions'
        permission_prefix = 'states'
        enum_spec = ('list_state_machines', 'stateMachines', None)
        arn = id = 'stateMachineArn'
        arn_service = 'states'
        arn_type = 'stateMachine'
        cfn_type = config_type = 'AWS::StepFunctions::StateMachine'
        name = 'name'
        date = 'creationDate'
        detail_spec = (
            "describe_state_machine", "stateMachineArn",
            'stateMachineArn', None)
        permissions_augment = ("states:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeStepFunction,
        'config': ConfigSource
    }


class DescribeActivity(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


@resources.register('sfn-activity')
class Activity(QueryResourceManager):
    """AWS Step Functions Activity

    :example:

    .. code-block:: yaml

            policies:
              - name: activity-encrypted-cmk
                resource: sfn-activity
                filters:
                  - not:
                    - type: kms-key
                      key: c7n:AliasName
                      value: alias/test/sfn/encrypted
              - name: activity-tag-untagged
                resource: sfn-activity
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    class resource_type(TypeInfo):
        service = 'stepfunctions'
        permission_prefix = 'states'
        enum_spec = ('list_activities', 'activities', None)
        arn = id = 'activityArn'
        arn_type = 'activity'
        cfn_type = config_type = 'AWS::StepFunctions::Activity'
        name = 'name'
        date = 'creationDate'
        detail_spec = (
            "describe_activity", "activityArn",
            'activityArn', None)
        permissions_augment = ("states:ListTagsForResource",)

    source_mapping = {
            'describe': DescribeActivity,
            'config': ConfigSource
        }


class InvokeStepFunction(Action):
    """Invoke step function on resources.

    By default this will invoke a step function for each resource
    providing both the `policy` and `resource` as input.

    That behavior can be configured setting policy and bulk
    boolean flags on the action.

    If bulk action parameter is set to true, then the step
    function will be invoked in bulk, with a set of resource arns
    under the `resources` key.

    The size of the batch can be configured via the batch-size
    parameter. Note step function state (input, execution, etc)must
    fit within 32k, we default to batch size 250.

    :example:

    .. code-block:: yaml

       policies:
         - name: invoke-step-function
           resource: s3
           filters:
             - is-log-target
             - "tag:IngestSetup": absent
           actions:
             - type: invoke-sfn
               # This will cause the workflow to be invoked
               # with many resources arns in a single execution.
               # Note this is *not* the default.
               bulk: true
               batch-size: 10
               state-machine: LogIngestSetup
    """

    schema = type_schema(
        'invoke-sfn',
        required=['state-machine'],
        **{'state-machine': {'type': 'string'},
           'batch-size': {'type': 'integer'},
           'bulk': {'type': 'boolean'},
           'policy': {'type': 'boolean'}})
    schema_alias = True
    permissions = ('states:StartExecution',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('stepfunctions')
        arn = self.data['state-machine']
        if not arn.startswith('arn'):
            arn = 'arn:aws:states:{}:{}:stateMachine:{}'.format(
                self.manager.config.region, self.manager.config.account_id, arn)

        params = {'stateMachineArn': arn}
        pinput = {}

        if self.data.get('policy', True):
            pinput['policy'] = dict(self.manager.data)

        resource_set = list(zip(self.manager.get_arns(resources), resources))
        if self.data.get('bulk', False) is True:
            return self.invoke_batch(client, params, pinput, resource_set)

        for arn, r in resource_set:
            pinput['resource'] = r
            params['input'] = dumps(pinput)
            r['c7n:execution-arn'] = self.manager.retry(
                client.start_execution, **params).get('executionArn')

    def invoke_batch(self, client, params, pinput, resource_set):
        for batch_rset in chunks(resource_set, self.data.get('batch-size', 250)):
            pinput['resources'] = [rarn for rarn, _ in batch_rset]
            params['input'] = dumps(pinput)
            exec_arn = self.manager.retry(
                client.start_execution, **params).get('executionArn')
            for _, r in resource_set:
                r['c7n:execution-arn'] = exec_arn

    @classmethod
    def register_resources(cls, registry, resource_class):
        if 'invoke-sfn' not in resource_class.action_registry:
            resource_class.action_registry.register('invoke-sfn', cls)


resources.subscribe(InvokeStepFunction.register_resources)


@StepFunction.action_registry.register('tag')
@Activity.action_registry.register('tag')
class TagStepFunction(Tag):
    """Action to create tag(s) on a step function

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-step-function
                resource: step-machine
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('states:TagResource',)

    def process_resource_set(self, client, resources, tags):
        mid = self.manager.resource_type.arn
        tags_lower = []

        for tag in tags:
            tags_lower.append({k.lower(): v for k, v in tag.items()})

        for r in resources:
            client.tag_resource(resourceArn=r[mid], tags=tags_lower)


@StepFunction.action_registry.register('remove-tag')
@Activity.action_registry.register('remove-tag')
class UnTagStepFunction(RemoveTag):
    """Action to create tag(s) on a step function

    :example:

    .. code-block:: yaml

            policies:
              - name: step-function-remove-tag
                resource: step-machine
                actions:
                  - type: remove-tag
                    tags: ["test"]
    """

    permissions = ('states:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        mid = self.manager.resource_type.arn
        for r in resources:
            client.untag_resource(resourceArn=r[mid], tagKeys=tag_keys)


@Activity.filter_registry.register('kms-key')
@StepFunction.filter_registry.register('kms-key')
class StepFunctionKmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = "encryptionConfiguration.kmsKeyId"
