# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('containerservice')
class ContainerService(ArmResourceManager):
    """Container Service Resource

    :example:

    Returns all container services that did not provision successfully

    .. code-block:: yaml

        policies:
        - name: broken-containerservices
          resource: azure.containerservice
          filters:
            - type: value
              key: properties.provisioningState
              op: not-equal
              value_type: normalize
              value: succeeded
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Containers']

        service = 'azure.mgmt.containerservice'
        client = 'ContainerServiceClient'
        enum_spec = ('container_services', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.agentPoolProfiles[].[name, vmSize, count]'
        )
        resource_type = 'Microsoft.ContainerService/containerServices'
