# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.compute.models import Sku, VirtualMachineScaleSetUpdate

from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('vmss')
class VMScaleSet(ArmResourceManager):
    """Virtual Machine Scale Set Resource

    :example:

    This policy will find all VM Scale Sets that are set to overprovision

    .. code-block:: yaml

        policies:
          - name: find-vmss-overprovision-true
            resource: azure.vmss
            filters:
              - type: value
                key: properties.overprovision
                op: equal
                value: True

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('virtual_machine_scale_sets', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name',
            'sku.capacity'
        )
        resource_type = 'Microsoft.Compute/virtualMachineScaleSets'


@VMScaleSet.action_registry.register('scale')
class VmssSetCapacityAction(AzureBaseAction):
    """Set the instance capacity of a VM Scale Set.

    :example:

    Scale VMSS down to 1 instance during off-hours and back up during on-hours:

    .. code-block:: yaml

        policies:
          - name: vmss-scale-down-offhours
            resource: azure.vmss
            filters:
              - type: offhour
                default_tz: utc
                offhour: 19
                onhour: 7
            actions:
              - type: scale
                capacity: 1

          - name: vmss-scale-up-onhours
            resource: azure.vmss
            filters:
              - type: onhour
                default_tz: utc
                offhour: 19
                onhour: 7
            actions:
              - type: scale
                capacity: 10

    """

    schema = type_schema(
        'scale',
        required=['capacity'],
        **{'capacity': {'type': 'integer', 'minimum': 0}}
    )

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        sku = resource.get('sku', {})
        self.client.virtual_machine_scale_sets.begin_update(
            resource['resourceGroup'],
            resource['name'],
            VirtualMachineScaleSetUpdate(
                sku=Sku(
                    name=sku.get('name'),
                    tier=sku.get('tier'),
                    capacity=self.data['capacity']
                )
            )
        )
