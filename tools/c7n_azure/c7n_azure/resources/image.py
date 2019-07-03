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


@resources.register('image')
class Image(ArmResourceManager):
    """Virtual Machine Image

    :example:

    Returns all virtual machine images named my-test-vm-image

    .. code-block:: yaml

        policies:
          - name: get-vm-image
            resource: azure.image
            filters:
              - type: value
                key: name
                op: eq
                value: my-test-vm-image

    """
    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('images', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
        )
        resource_type = 'Microsoft.Compute/images'
