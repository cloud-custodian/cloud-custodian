# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from netaddr import IPSet


@resources.register('eventhub')
class EventHub(ArmResourceManager):
    """Event Hub Resource

    :example:

    This policy will find all Event Hubs allowing traffic from 1.2.2.128/25 CIDR.

    .. code-block:: yaml

        policies:
          - name: find-event-hub-allowing-subnet
            resource: azure.eventhub
            filters:
              - type: firewall-rules
                include:
                    - '1.2.2.128/25'

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Events']

        service = 'azure.mgmt.eventhub'
        client = 'EventHubManagementClient'
        enum_spec = ('namespaces', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name',
            'properties.isAutoInflateEnabled'
        )
        resource_type = 'Microsoft.EventHub/namespaces'


@EventHub.filter_registry.register('firewall-rules')
class EventHubFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(EventHubFirewallRulesFilter, self).__init__(data, manager)
        self.client = None

    def process(self, resources, event=None):
        self.client = self.manager.get_client()
        return super(EventHubFirewallRulesFilter, self).process(resources, event)

    def _query_rules(self, resource):
        query = self.client.namespaces.get_network_rule_set(
            resource['resourceGroup'],
            resource['name'])

        resource_rules = IPSet([r.ip_mask for r in query.ip_rules])

        return resource_rules
