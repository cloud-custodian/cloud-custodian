# Copyright 2019 Microsoft Corporation
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

from azure.mgmt.compute.models import VirtualMachineUpdate
from azure.mgmt.resource.resources.models import GenericResource


def get_policy(actions=None, filters=None):
    policy = {'name': 'test-tag',
              'resource': 'azure.resourcegroup'}
    if filters:
        policy['filters'] = filters
    if actions:
        policy['actions'] = actions
    return policy


def get_policy_event_grid(actions):
    return {'name': 'test-tag',
            'resource': 'azure.resourcegroup',
            'mode': {
                'type': 'azure-event-grid',
                'events': [
                    {
                        'resourceProvider': 'Microsoft.Resources/subscriptions/resourceGroups',
                        'event': 'write'
                    }
                ]},
            'actions': actions}


def get_resource(existing_tags):
    resource = GenericResource(tags=existing_tags).serialize()
    resource['id'] = '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/' \
                     'TEST_VM/providers/Microsoft.Compute/virtualMachines/cctestvm'
    resource['name'] = 'cctestvm'
    resource['type'] = 'Microsoft.Compute/virtualMachines'
    resource['InstanceId'] = "testInstance"
    return resource


def get_resource_group_resource(existing_tags):
    resource = GenericResource(tags=existing_tags).serialize()
    resource['id'] = '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/test_rg'
    resource['name'] = 'test_rg'
    resource['type'] = 'resourceGroups'
    return resource


def get_tags_parameter(update_tags_mock):
    assert(len(update_tags_mock.call_args_list) == 1)
    assert(len(update_tags_mock.call_args_list[0][0]) == 3)
    return update_tags_mock.call_args_list[0][0][2]


def get_tags(client, rg_name, vm_name):
    return client.virtual_machines.get(rg_name, vm_name).tags


def set_tags(client, rg_name, vm_name, tags):
    client.virtual_machines.update(rg_name, vm_name, VirtualMachineUpdate(tags=tags))
