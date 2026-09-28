# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('private-dns-zone')
class PrivateDnsZone(ArmResourceManager):
    """Private DNS Zone Resource

    :example:

    Finds all Private DNS Zones in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-private-dns-zones
              resource: azure.private-dns-zone

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.privatedns'
        client = 'PrivateDnsManagementClient'
        enum_spec = ('private_zones', 'list', {})
        resource_type = 'Microsoft.Network/privateDnsZones'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.numberOfRecordSets',
            'properties.numberOfVirtualNetworkLinks'
        )
