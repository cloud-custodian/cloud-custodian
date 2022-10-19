# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('service-fabric-cluster')
class ServiceFabricCluster(ArmResourceManager):
    """Azure Servic Fabric Cluster Resource

    :example:

    Returns all Service Fabric clusters

    .. code-block:: yaml

        policies:
          - name: service-fabric-clusters
            resource: azure.service-fabric-cluster

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.servicefabric'
        client = 'ServiceFabricManagementClient'
        enum_spec = ('clusters', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.ServiceFabric/clusters'


@resources.register('service-fabric-cluster-managed')
class ServiceFabricClusterManaged(ArmResourceManager):
    """Azure Servic Fabric Managed Cluster Resource

    :example:

    Returns all managed Service Fabric clusters

    .. code-block:: yaml

        policies:
          - name: service-fabric-clusters
            resource: azure.service-fabric-cluster-managed

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.servicefabric'
        client = 'ServiceFabricManagementClient'
        enum_spec = ('managed_clusters', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.ServiceFabric/clusters'
