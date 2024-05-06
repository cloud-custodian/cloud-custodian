# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from azure.mgmt.compute.models import HardwareProfile, VirtualMachineUpdate
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter
from c7n.utils import local_session


@resources.register('vm')
class VirtualMachine(ArmResourceManager):
    """Virtual Machine Resource

    :example:

    Stop all running VMs

    .. code-block:: yaml

        policies:
          - name: stop-running-vms
            resource: azure.vm
            filters:
              - type: instance-view
                key: statuses[].code
                op: in
                value_type: swap
                value: PowerState/running
            actions:
              - type: stop

    :example:

    Start all VMs

    .. code-block:: yaml

        policies:
          - name: start-vms
            resource: azure.vm
            actions:
              - type: start

    :example:

    Restart all VMs

    .. code-block:: yaml

        policies:
          - name: start-vms
            resource: azure.vm
            actions:
              - type: restart

    :example:

    Resize specific VM by name

    .. code-block:: yaml

        policies:
          - name: resize-vm
            resource: azure.vm
            filters:
              - type: value
                key: name
                op: eq
                value_type: normalize
                value: fake_vm_name
            actions:
              - type: resize
                vmSize: Standard_A2_v2

    :example:

    Delete specific VM by name

    .. code-block:: yaml

        policies:
          - name: delete-vm
            resource: azure.vm
            filters:
              - type: value
                key: name
                op: eq
                value_type: normalize
                value: fake_vm_name
            actions:
              - type: delete

    :example:

    Find all VMs with a Public IP address

    .. code-block:: yaml

        policies:
          - name: vms-with-public-ip
            resource: azure.vm
            filters:
              - type: network-interface
                key: 'properties.ipConfigurations[].properties.publicIPAddress.id'
                value: not-null

    :example:

    This policy will find all VMs that have Percentage CPU usage >= 75% over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: busy-vms
            resource: azure.vm
            filters:
              - type: metric
                metric: Percentage CPU
                op: ge
                aggregation: average
                threshold: 75
                timeframe: 72

    :example:

    This policy will find all VMs that have Percentage CPU usage <= 1% over the last 72 hours,
    mark for deletion in 7 days

    .. code-block:: yaml

        policies:
          - name: delete-unused-vms
            resource: azure.vm
            filters:
              - type: metric
                metric: Percentage CPU
                op: le
                aggregation: average
                threshold: 1
                timeframe: 72
             actions:
              - type: mark-for-op
                op: delete
                days: 7

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

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
        resource_type = 'Microsoft.Compute/virtualMachines'


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


@VirtualMachine.filter_registry.register('vm-extensions')
class VMExtensionsFilter(ValueFilter):
    """
        Provides a value filter targetting the virtual machine
        extensions array.  Requires an additional API call per
        virtual machine to retrieve the extensions.

        Here is an example of the data returned:

        .. code-block:: json

          [{
            "id": "/subscriptions/...",
            "name": "CustomScript",
            "type": "Microsoft.Compute/virtualMachines/extensions",
            "location": "centralus",
            "properties": {
              "publisher": "Microsoft.Azure.Extensions",
              "type": "CustomScript",
              "typeHandlerVersion": "2.0",
              "autoUpgradeMinorVersion": true,
              "settings": {
                "fileUris": []
              },
              "provisioningState": "Succeeded"
            }
          }]

        :examples:

        Find VM's with Custom Script extensions

        .. code-block:: yaml

            policies:
              - name: vm-with-customscript
                description: |
                  Find all virtual machines with a custom
                  script extension installed.
                resource: azure.vm
                filters:
                  - type: vm-extensions
                    op: in
                    key: "[].properties.type"
                    value: CustomScript
                    value_type: swap


        Find VM's without the OMS agent installed

        .. code-block:: yaml

            policies:
              - name: vm-without-oms
                description: |
                  Find all virtual machines without the
                  OMS agent installed.
                resource: azure.vm
                filters:
                  - type: vm-extensions
                    op: not-in
                    key: "[].properties.type"
                    value: OmsAgentForLinux
                    value_type: swap

        """
    schema = type_schema('vm-extensions', rinherit=ValueFilter.schema)
    annotate = False  # cannot annotate arrays

    def __call__(self, i):
        if 'c7n:vm-extensions' not in i:
            client = self.manager.get_client()
            extensions = (
                client.virtual_machine_extensions
                .list(i['resourceGroup'], i['name'])
            )
            i['c7n:vm-extensions'] = [e.serialize(True) for e in extensions.value]

        return super(VMExtensionsFilter, self).__call__(i['c7n:vm-extensions'])


@VirtualMachine.filter_registry.register('network-interface')
class NetworkInterfaceFilter(RelatedResourceFilter):

    schema = type_schema('network-interface', rinherit=ValueFilter.schema)

    RelatedResource = "c7n_azure.resources.network_interface.NetworkInterface"
    RelatedIdsExpression = "properties.networkProfile.networkInterfaces[0].id"


@VirtualMachine.filter_registry.register('backup-status')
class BackupStatusFilter(ValueFilter):
    """Filters Virtual Machines by their backup protection status.

    :example:

    This policy will get Virtual Machine resources that Protected backup protection status.

    .. code-block:: yaml

        policies:
          - name: vm-backup-status-protected
            resource: azure.vm
            filters:
              - type: backup-status
                key: protectionStatus
                value: Protected
    """
    schema = type_schema(
        'backup-status',
        rinherit=ValueFilter.schema
    )

    backup_annotation_key = "c7n:BackupStatus"
    annotate = False

    def process(self, resources, event=None):
        s = local_session(self.manager.session_factory)
        client = s.client('azure.mgmt.recoveryservicesbackup.RecoveryServicesBackupClient')

        for resource in resources:
            if self.backup_annotation_key in resource:
                continue
            resource[self.backup_annotation_key] = client.backup_status.get(
                azure_region=resource['location'],
                parameters=dict(resourceId=resource['id'], resourceType='VM')
            ).serialize(True)
        return super().process(resources, event)

    def __call__(self, r):
        return super().__call__(r[self.backup_annotation_key])


@VirtualMachine.action_registry.register('poweroff')
class VmPowerOffAction(AzureBaseAction):

    schema = type_schema('poweroff')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.begin_power_off(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('stop')
class VmStopAction(AzureBaseAction):

    schema = type_schema('stop')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.begin_deallocate(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('start')
class VmStartAction(AzureBaseAction):

    schema = type_schema('start')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.begin_start(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('restart')
class VmRestartAction(AzureBaseAction):

    schema = type_schema('restart')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.virtual_machines.begin_restart(resource['resourceGroup'], resource['name'])


@VirtualMachine.action_registry.register('resize')
class VmResizeAction(AzureBaseAction):

    """Change a VM's size

    :example:

    Resize specific VM by name

    .. code-block:: yaml

        policies:
          - name: resize-vm
            resource: azure.vm
            filters:
              - type: value
                key: name
                op: eq
                value_type: normalize
                value: fake_vm_name
            actions:
              - type: resize
                vmSize: Standard_A2_v2
    """

    schema = type_schema(
        'resize',
        required=['vmSize'],
        **{
            'vmSize': {'type': 'string'}
        })

    def __init__(self, data, manager=None):
        super(VmResizeAction, self).__init__(data, manager)
        self.vm_size = self.data['vmSize']

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        hardware_profile = HardwareProfile(vm_size=self.vm_size)

        self.client.virtual_machines.begin_update(
            resource['resourceGroup'],
            resource['name'],
            VirtualMachineUpdate(hardware_profile=hardware_profile)
        )
