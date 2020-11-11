# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('dnszone')
class DnsZone(ArmResourceManager):
    """DNS Zone Resource

    :example:

    Finds all DNS Zones in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-dns-zones
              resource: azure.dnszone

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.dns'
        client = 'DnsManagementClient'
        enum_spec = ('zones', 'list', {})
        resource_type = 'Microsoft.Network/dnszones'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.numberOfRecordSets',
            'properties.nameServers'
        )
