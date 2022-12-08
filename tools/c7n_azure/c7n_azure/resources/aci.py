# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('container-group')
class ContainerGroup(ArmResourceManager):
    """Container Group Resource

    :example:

    .. code-block:: yaml

        policies:
          - name: aci
            resource: azure.container-group
            filters:
              - type: value
                key: properties.virtualNetworkType
                op: eq
                value: None
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Containers']

        service = 'azure.mgmt.containerinstance'
        client = 'ContainerInstanceManagementClient'
        enum_spec = ('container_groups', 'list', None)
        resource_type = 'Microsoft.ContainerInstance/containerGroups'
