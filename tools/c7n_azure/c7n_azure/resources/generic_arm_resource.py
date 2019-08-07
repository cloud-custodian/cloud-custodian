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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, arm_resource_types
from c7n_azure.utils import ResourceIdParser
from c7n.filters.core import Filter, type_schema


@resources.register('armresource')
class GenericArmResource(ArmResourceManager):
    """Azure Arm Resource

    :example:

    This policy will find all ARM resources with the tag 'Tag1' present

    .. code-block:: yaml

        policies
          - name: find-resources-with-Tag1
            resource: azure.armresource
            filters:
              - tag:Tag1: present

    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Generic']

        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)
        resource_type = 'armresource'
        enable_tag_operations = True

    def tag_operation_enabled(self, resource_type):
        if resource_type.lower() in arm_resource_types:
            return arm_resource_types[resource_type.lower()].enable_tag_operations
        return False


@GenericArmResource.filter_registry.register('resource-type')
class ResourceTypeFilter(Filter):
    schema = type_schema('resource-type',
                         required=['values'],
                         values={'type': 'array', 'items': {'type': 'string'}})

    def __init__(self, data, manager=None):
        super(ResourceTypeFilter, self).__init__(data, manager)
        self.allowed_types = [t.lower() for t in self.data['values']]

    def process(self, resources, event=None):
        result = []
        for r in resources:
            if 'id' in r:
                t = ResourceIdParser.get_full_type(r['id'])
                if t.lower() in self.allowed_types:
                    result.append(r)

        return result
