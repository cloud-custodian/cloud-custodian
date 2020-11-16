# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('recordset')
class RecordSet(ChildArmResourceManager):
    """Record Set Resource

    :example:

    Finds all Record Sets for all DNS Zones in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-record-sets
              resource: azure.recordset

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.dns'
        client = 'DnsManagementClient'
        enum_spec = ('record_sets', 'list_by_dns_zone', None)
        parent_manager_name = 'dnszone'
        default_report_fields = (
            'name',
            'type',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        # NOTE: Record Sets each have their own resource_type value
        resource_type = 'Microsoft.Network/dnszones/{A|AAAA|CAA|CNAME|LIST|MX|NS|PTR|SOA|SRV|TXT}'

        enable_tag_operations = False

        @classmethod
        def extra_args(cls, dns_zone):
            return {
                'resource_group_name': dns_zone['resourceGroup'],
                'zone_name': dns_zone['name']
            }
