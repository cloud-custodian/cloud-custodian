# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('aks')
class KubernetesService(ArmResourceManager):
    """Azure Kubernetes Service Resource

    :example:

    Returns all aks clusters that did not provision successfully

    .. code-block:: yaml

        policies:
          - name: broken-aks
            resource: azure.aks
            filters:
              - type: value
                key: properties.provisioningState
                op: not-equal
                value_type: normalize
                value: succeeded

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute', 'Containers']

        service = 'azure.mgmt.containerservice'
        client = 'ContainerServiceClient'
        enum_spec = ('managed_clusters', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.kubernetesVersion',
            'properties.agentPoolProfiles[][name, count]'
        )
        resource_type = 'Microsoft.ContainerService/managedClusters'
