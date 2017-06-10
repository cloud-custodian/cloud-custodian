# Copyright 2016 Capital One Services, LLC
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

import logging

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


log = logging.getLogger('custodian.cfn')

filters = FilterRegistry('cfn.filters')
actions = ActionRegistry('cfn.actions')


@resources.register('cfn')
class CloudFormation(QueryResourceManager):

    class resource_type(object):
        service = 'cloudformation'
        type = 'stack'
        enum_spec = ('describe_stacks', 'Stacks[]', None)
        id = 'StackName'
        filter_name = 'StackName'
        filter_type = 'scalar'
        name = 'StackName'
        date = 'CreationTime'
        dimension = None

    action_registry = actions
    filter_registry = filters


@actions.register('delete')
class Delete(BaseAction):
    """Action to delete cloudformation stacks

    It is recommended to use a filter to avoid unwanted deletion of stacks

    :example:

        .. code-block: yaml

            policies:
              - name: cloudformation-delete-failed-stacks
                resource: cfn
                filters:
                  - StackStatus: ROLLBACK_COMPLETE
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("cloudformation:DeleteStack",)

    def process(self, stacks):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_stacks, stacks))

    def process_stacks(self, stack):
        client = local_session(
            self.manager.session_factory).client('cloudformation')
        client.delete_stack(StackName=stack['StackName'])
