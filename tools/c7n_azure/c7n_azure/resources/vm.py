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
from c7n_azure.actions import AzureBaseAction
from c7n_azure.filters import AzureOffHour, AzureOnHour
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter


@resources.register('vm')
class VirtualMachine(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('virtual_machines', 'list_all', None)
        diagnostic_settings_enabled = False
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.hardwareProfile.vmSize',
        )

    @staticmethod
    def register(registry, _):
        # Additional filters/actions registered for this resource type
        VirtualMachine.filter_registry.register("offhour", AzureOffHour)
        VirtualMachine.filter_registry.register("onhour", AzureOnHour)


resources.subscribe(resources.EVENT_FINAL, VirtualMachine.register)


@VirtualMachine.filter_registry.register('instance-view')
class InstanceViewFilter(ValueFilter):
    schema = type_schema('instance-view', rinherit=ValueFilter.schema)

    def __call__(self, i):
        if 'instanceView' not in i:
            client = self.manager.get_client()
            instance = (
                client.virtual_machines
                .get(i['resourceGroup'], i['name'], expand='instanceview')
                .instance_view
            )
            i['instanceView'] = instance.serialize()

        return super(InstanceViewFilter, self).__call__(i['instanceView'])


@VirtualMachine.filter_registry.register('network-interface')
class NetworkInterfaceFilter(RelatedResourceFilter):

    schema = type_schema('network-interface', rinherit=ValueFilter.schema)

    RelatedResource = "c7n_azure.resources.network_interface.NetworkInterface"
    RelatedIdsExpression = "properties.networkProfile.networkInterfaces[0].id"


@VirtualMachine.action_registry.register('poweroff')
class VmPowerOffAction(AzureBaseAction):

    schema = type_schema('poweroff')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.power_off(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('stop')
class VmStopAction(AzureBaseAction):

    schema = type_schema('stop')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.deallocate(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('start')
class VmStartAction(AzureBaseAction):

    schema = type_schema('start')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.start(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('restart')
class VmRestartAction(AzureBaseAction):

    schema = type_schema('restart')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.restart(resource['resourceGroup'], resource['name'])
