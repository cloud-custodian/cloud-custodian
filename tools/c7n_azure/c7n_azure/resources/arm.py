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
from c7n_azure.actions.delete import DeleteAction
from c7n_azure.actions.lock import LockAction
from c7n_azure.actions.tagging import (AutoTagDate)
from c7n_azure.actions.tagging import Tag, AutoTagUser, RemoveTag, TagTrim, TagDelayedAction
from c7n_azure.filters import (CostFilter, MetricFilter, TagActionFilter,
                               DiagnosticSettingsFilter, PolicyCompliantFilter, ResourceLockFilter,
                               AzureOffHour, AzureOnHour)
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, ChildResourceManager, TypeInfo, \
    ChildTypeInfo, TypeMeta
from c7n_azure.utils import ResourceIdParser

from c7n.utils import local_session

arm_resource_types = {}


@six.add_metaclass(TypeMeta)
class ArmTypeInfo(TypeInfo):
    # api client construction information for ARM resources
    id = 'id'
    name = 'name'
    diagnostic_settings_enabled = True
    default_report_fields = (
        'name',
        'location',
        'resourceGroup'
    )
    resource_type = None
    enable_tag_operations = True


@six.add_metaclass(QueryMeta)
class ArmResourceManager(QueryResourceManager):
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

    class resource_type(ArmTypeInfo):
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources

    def get_resources(self, resource_ids):
        resource_client = self.get_client('azure.mgmt.resource.ResourceManagementClient')
        session = local_session(self.session_factory)
        data = [
            resource_client.resources.get_by_id(rid, session.resource_api_version(rid))
            for rid in resource_ids
        ]
        return self.augment([r.serialize(True) for r in data])

    def tag_operation_enabled(self, resource_type):
        return self.resource_type.enable_tag_operations

    @staticmethod
    def register_arm_specific(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            if issubclass(klass, ArmResourceManager):
                arm_resource_types[klass.resource_type.resource_type.lower()] = klass.resource_type

                if klass.resource_type.enable_tag_operations:
                    klass.action_registry.register('tag', Tag)
                    klass.action_registry.register('untag', RemoveTag)
                    klass.action_registry.register('auto-tag-user', AutoTagUser)
                    klass.action_registry.register('auto-tag-date', AutoTagDate)
                    klass.action_registry.register('tag-trim', TagTrim)
                    klass.filter_registry.register('marked-for-op', TagActionFilter)
                    klass.action_registry.register('mark-for-op', TagDelayedAction)

                if resource != 'armresource':
                    klass.filter_registry.register('cost', CostFilter)

                klass.filter_registry.register('metric', MetricFilter)
                klass.filter_registry.register('policy-compliant', PolicyCompliantFilter)
                klass.filter_registry.register('resource-lock', ResourceLockFilter)
                klass.action_registry.register('lock', LockAction)
                klass.filter_registry.register('offhour', AzureOffHour)
                klass.filter_registry.register('onhour', AzureOnHour)

                if resource != 'resourcegroup':
                    klass.action_registry.register('delete', DeleteAction)

                if klass.resource_type.diagnostic_settings_enabled:
                    klass.filter_registry.register('diagnostic-settings', DiagnosticSettingsFilter)


@six.add_metaclass(QueryMeta)
class ChildArmResourceManager(ChildResourceManager, ArmResourceManager):

    class resource_type(ChildTypeInfo, ArmTypeInfo):
        pass


resources.subscribe(resources.EVENT_FINAL, ArmResourceManager.register_arm_specific)
