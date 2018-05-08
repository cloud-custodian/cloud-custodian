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

import six
from c7n_azure.query import QueryResourceManager, QueryMeta
from c7n_azure.actions import Tag, AutoTagUser, RemoveTag
from c7n_azure.utils import ResourceIdParser
from c7n_azure.provider import resources


@resources.register('armresource')
@six.add_metaclass(QueryMeta)
class ArmResourceManager(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list')
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources

    @staticmethod
    def register_arm_specific(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            if issubclass(klass, ArmResourceManager):
                klass.action_registry.register('tag', Tag)
                klass.action_registry.register('untag', RemoveTag)
                klass.action_registry.register('auto-tag-user', AutoTagUser)


resources.subscribe(resources.EVENT_FINAL, ArmResourceManager.register_arm_specific)
