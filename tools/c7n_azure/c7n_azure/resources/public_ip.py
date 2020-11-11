# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('publicip')
class PublicIPAddress(ArmResourceManager):
    """Public IP Resource

    :example:

    This policy will find all public IP addresses under DDoS attack over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: publicip-dropping-packets
            resource: azure.publicip
            filters:
              - type: metric
                metric: IfUnderDDoSAttack
                op: gt
                aggregation: maximum
                threshold: 0
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('public_ip_addresses', 'list_all', None)
        type = 'publicip'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.publicIPAddressVersion',
            'properties.publicIPAllocationMethod',
            'properties.ipAddress'
        )
        resource_type = 'Microsoft.Network/publicIPAddresses'
