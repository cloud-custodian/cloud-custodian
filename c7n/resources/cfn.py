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

import logging

from concurrent.futures import as_completed

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag

log = logging.getLogger('custodian.cfn')


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
        config_type = 'AWS::CloudFormation::Stack'


@CloudFormation.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete cloudformation stacks

    It is recommended to use a filter to avoid unwanted deletion of stacks

    :example:

    .. code-block:: yaml

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


@CloudFormation.action_registry.register('set-protection')
class SetProtection(BaseAction):
    """Action to disable termination protection

    It is recommended to use a filter to avoid unwanted deletion of stacks

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudformation-disable-protection
                resource: cfn
                filters:
                  - StackStatus: CREATE_COMPLETE
                actions:
                  - type: set-protection
                    state: False
    """

    schema = type_schema(
        'set-protection', state={'type': 'boolean', 'default': False})

    permissions = ('cloudformation:UpdateStack',)

    def process(self, stacks):
        client = local_session(
            self.manager.session_factory).client('cloudformation')

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for s in stacks:
                futures[w.submit(self.process_stacks, client, s)] = s
            for f in as_completed(futures):
                s = futures[f]
                if f.exception():
                    self.log.error(
                        "Error updating protection stack:%s error:%s",
                        s['StackName'], f.exception())

    def process_stacks(self, client, stack):
        client.update_termination_protection(
            EnableTerminationProtection=self.data.get('state', False),
            StackName=stack['StackName'])


@CloudFormation.action_registry.register('tag')
class CloudFormationAddTag(Tag):
    """Action to tag a cloudformation stack

    :example:

    .. code-block: yaml

        policies:
          - name: add-cfn-tag
            resource: cfn
            filters:
              - 'tag:DesiredTag': absent
            actions:
              - type: tag
                key: DesiredTag
                value: DesiredValue
    """
    permissions = ('cloudformation:UpdateStack',)

    def process_resource_set(self, stacks, tags):
        client = local_session(
            self.manager.session_factory).client('cloudformation')

        def _tag_stacks(s):
            client.update_stack(
                StackName=s['StackName'],
                UsePreviousTemplate=True,
                Tags=tags)

        with self.executor_factory(max_workers=2) as w:
            list(w.map(_tag_stacks, stacks))


@CloudFormation.action_registry.register('remove-tag')
class CloudFormationRemoveTag(RemoveTag):
    """Action to remove tags from a cloudformation stack

    :example:

    .. code-block: yaml

        policies:
          - name: add-cfn-tag
            resource: cfn
            filters:
              - 'tag:DesiredTag': present
            actions:
              - type: remove-tag
                tags: ['DesiredTag']
    """

    def process_resource_set(self, stacks, keys):
        client = local_session(
            self.manager.session_factory).client('cloudformation')

        def _remove_tag(s):
            tags = [t for t in s['Tags'] if t['Key'] not in keys]
            client.update_stack(
                StackName=s['StackName'],
                UsePreviousTemplate=True,
                Tags=tags)

        with self.executor_factory(max_workers=2) as w:
            list(w.map(_remove_tag, stacks))
