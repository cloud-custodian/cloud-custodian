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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.tags import TagHelper

from c7n.actions import BaseAction
from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter

from c7n.filters.offhours import OffHour, OnHour


@resources.register('vm')
class VirtualMachine(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('virtual_machines', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.hardwareProfile.vmSize',
        )


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
class VmPowerOffAction(BaseAction):

    schema = type_schema('poweroff')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(VmPowerOffAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def poweroff(self, resource_group, vm_name):
        self.client.virtual_machines.power_off(resource_group, vm_name)

    def process(self, vms):
        for vm in vms:
            self.poweroff(vm['resourceGroup'], vm['name'])


@VirtualMachine.action_registry.register('stop')
class VmStopAction(BaseAction):

    schema = type_schema('stop')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(VmStopAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def stop(self, resource_group, vm_name):
        self.client.virtual_machines.deallocate(resource_group, vm_name)

    def process(self, vms):
        for vm in vms:
            self.stop(vm['resourceGroup'], vm['name'])


@VirtualMachine.action_registry.register('start')
class VmStartAction(BaseAction):

    schema = type_schema('start')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(VmStartAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def start(self, resource_group, vm_name):
        self.client.virtual_machines.start(resource_group, vm_name)

    def process(self, vms):
        for vm in vms:
            self.start(vm['resourceGroup'], vm['name'])


@VirtualMachine.action_registry.register('restart')
class VmRestartAction(BaseAction):

    schema = type_schema('restart')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(VmRestartAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def restart(self, resource_group, vm_name):
        self.client.virtual_machines.restart(resource_group, vm_name)

    def process(self, vms):
        for vm in vms:
            self.restart(vm['resourceGroup'], vm['name'])


@VirtualMachine.filter_registry.register('offhour')
class AzureVMOffHour(OffHour):

    # Override get_tag_value because Azure stores tags differently from AWS
    def get_tag_value(self, i):
        tag_value = TagHelper.get_tag_value(resource=i,
                                       tag=self.tag_key,
                                       utf_8=True)

        if tag_value is not False:
            tag_value = tag_value.lower().strip("'\"")
        return tag_value


@VirtualMachine.filter_registry.register('onhour')
class AzureVMOnHour(OnHour):

    # Override get_tag_value because Azure stores tags differently from AWS
    def get_tag_value(self, i):
        tag_value = TagHelper.get_tag_value(resource=i,
                                       tag=self.tag_key,
                                       utf_8=True)

        if tag_value is not False:
            tag_value = tag_value.lower().strip("'\"")
        return tag_value
