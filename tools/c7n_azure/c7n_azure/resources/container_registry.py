# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('containerregistry')
class ContainerRegistry(ArmResourceManager):
    """Container Registry Resource

    :example:

    Returns all container registry named my-test-container-registry

    .. code-block:: yaml

        policies:
        - name: get-container-registry
          resource: azure.containerregistry
          filters:
            - type: value
              key: name
              op: eq
              value: my-test-container-registry

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Containers']

        service = 'azure.mgmt.containerregistry'
        client = 'ContainerRegistryManagementClient'
        enum_spec = ('registries', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.ContainerRegistry/registries'
