# Copyright 2018 Capital One Services, LLC
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

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.utils import type_schema


@resources.register('resourcegroup')
class ResourceGroup(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resource_groups', 'list')


@ResourceGroup.filter_registry.register('empty-group')
class EmptyGroup(Filter):
    # policies:
    #   - name: test - azure
    #   resource: azure.resourcegroup
    #   filters:
    #       - type: empty-group

    def __call__(self, group):
        resources_iterator = (
            self.manager
                .get_client()
                .resources
                .list_by_resource_group(group['name'])
        )
        return not any(True for _ in resources_iterator)


@ResourceGroup.action_registry.register('delete')
class DeleteResourceGroup(BaseAction):
    # policies:
    #   - name: test - azure
    #   resource: azure.resourcegroup
    #   actions:
    #       - type: delete

    schema = type_schema('delete')

    def process(self, groups):
        for group in groups:
            self.manager.log.info('Removing empty resource group ' + group['name'])
            self.manager.get_client().resource_groups.delete(group['name'])
