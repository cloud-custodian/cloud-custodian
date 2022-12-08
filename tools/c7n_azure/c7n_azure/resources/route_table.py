# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('routetable')
class RouteTable(ArmResourceManager):
    """Route Table Resource

    :example:

    Finds all Route Tables in the subscription.

    .. code-block:: yaml

        policies:
            - name: find-all-route-tables
              resource: azure.routetable

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('route_tables', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.subnets[].id'
        )
        resource_type = 'Microsoft.Network/routeTables'
