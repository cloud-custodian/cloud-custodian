# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
