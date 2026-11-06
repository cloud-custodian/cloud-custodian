# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('private-record-set')
class PrivateRecordSet(ChildArmResourceManager):
    """Private DNS Record Set Resource

    :example:

    Finds all Record Sets for all Private DNS Zones in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-private-record-sets
              resource: azure.private-record-set

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.privatedns'
        client = 'PrivateDnsManagementClient'
        enum_spec = ('record_sets', 'list', None)
        parent_manager_name = 'private-dns-zone'
        default_report_fields = (
            'name',
            'type',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        # NOTE: Record Sets each have their own resource_type value. Private
        # zones support fewer record types than public zones.
        resource_type = 'Microsoft.Network/privateDnsZones/' \
                        '{A|AAAA|CNAME|MX|PTR|SOA|SRV|TXT}'

        @classmethod
        def extra_args(cls, private_dns_zone):
            return {
                'resource_group_name': private_dns_zone['resourceGroup'],
                'private_zone_name': private_dns_zone['name']
            }
