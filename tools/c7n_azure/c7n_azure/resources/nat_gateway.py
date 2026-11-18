# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('nat-gateway')
class NatGateway(ArmResourceManager):
    """NAT Gateway Resource

    :example:

    This policy will find NAT Gateways that are not attached to any subnet
    and have no public IP address or public IP prefix. They still cost money
    but cannot route any traffic.

    .. code-block:: yaml

        policies:
          - name: unattached-nat-gateways
            resource: azure.nat-gateway
            filters:
              - type: value
                key: properties.subnets
                value: empty
              - type: value
                key: properties.publicIpAddresses
                value: empty
              - type: value
                key: properties.publicIpPrefixes
                value: empty

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('nat_gateways', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name',
            'properties.idleTimeoutInMinutes'
        )
        resource_type = 'Microsoft.Network/natGateways'
