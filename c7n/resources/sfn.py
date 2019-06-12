# Copyright 2015-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import Tag, RemoveTag
from c7n.utils import type_schema, local_session


@resources.register('step-machine')
class StepFunction(QueryResourceManager):
    """AWS Step Functions State Machine"""

    class resource_type(object):
        service = 'stepfunctions'
        enum_spec = ('list_state_machines', 'stateMachines', None)
        arn = id = 'stateMachineArn'
        name = 'name'
        date = 'creationDate'
        dimension = None
        detail_spec = (
            "describe_state_machine", "stateMachineArn",
            'stateMachineArn', None)
        filter_name = None


class InvokeStepFunction(Action):
    """Invoke step function on resource.
    """

    schema = type_schema(
        'invoke-sfn',
        required=['state-machine'],
        **{'state-machine': {'type': 'string'},
           'resource': {'type': 'boolean'},
           'policy': {'type': 'boolean'}})
    schema_alias = True
    permissions = ('stepfunctions:StartExecution',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('stepfunctions')
        arn = self.data['state-machine']
        if not arn.startswith('arn'):
            arn = 'arn:aws:states:{}:{}:stateMachine:{}'.format(
                self.manager.ctx.region, self.manager.ctx.account_id, arn)
        params = {'stateMachineArn': arn}
        for arn, r in zip(self.manager.get_arns(resources), resources):
            pinput = {}
            if self.data.get('policy', True):
                pinput['policy'] = dict(self.manager.data)
            pinput['resource'] = self.data.get('resource', True) and dict(r) or arn
            params['input'] = pinput
            r['c7n:execution-arn'] = self.manager.retry(
                client.start_execution, **params).get('executionArn')

    @classmethod
    def register(cls, registry, key):
        for r in registry.values():
            r.action_registry.register('invoke-sfn', cls)


resources.register(InvokeStepFunction.register, resources.EVENT_FINAL)


@StepFunction.action_registry.register('tag')
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

    permissions = ('stepfunctions:TagResource',)

    def process_resource_set(self, client, resources, tags):

        tags_lower = []

        for tag in tags:
            tags_lower.append({k.lower(): v for k, v in tag.items()})

        for r in resources:
            client.tag_resource(resourceArn=r['stateMachineArn'], tags=tags_lower)


@StepFunction.action_registry.register('remove-tag')
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

    permissions = ('stepfunctions:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):

        for r in resources:
            client.untag_resource(resourceArn=r['stateMachineArn'], tagKeys=tag_keys)
