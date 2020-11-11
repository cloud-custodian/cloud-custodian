# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
        doc_groups = ['Compute']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('images', 'list', None)
        resource_type = 'Microsoft.Compute/images'
