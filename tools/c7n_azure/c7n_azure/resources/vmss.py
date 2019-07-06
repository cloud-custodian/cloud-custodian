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
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('virtual_machine_scale_sets', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Compute/virtualMachineScaleSets'
