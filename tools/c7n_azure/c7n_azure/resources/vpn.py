# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser
from msrestazure.tools import parse_resource_id
from c7n.filters import Filter
from c7n.utils import type_schema

@resources.register('vpn')
class VPN(ChildArmResourceManager):
    """VPN Gateway

    :example:

    Finds all vpn configured without custon ipsec

    .. code-block:: yaml

        policies:
          - name: vpn
            description: |
              Find all containers with public access enabled
            resource: azure.storage-container
            filters:
              - type: value
                key: properties.publicAccess
                op: not-equal
                value: None   # Possible values: Blob, Container, None
    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['VPN']
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('virtual_network_gateways', 'list', None)
        parent_manager_name = 'vnet'
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Network/virtualNetworkGateways'
        raise_on_exception = False
        default_report_fields = (
            'name',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup']}

    def get_resources(self, resource_ids):
        client = self.get_client()
        data = [
            self.virtual_network_gateways(rid, client)
            for rid in resource_ids
        ]
        return self.augment([r.serialize(True) for r in data])

    def get_virtual_network_gateways(self, resource_id, client):
        parsed = parse_resource_id(resource_id)
        return client.virtual_network_gateways.list(parsed.get('resource_group'))


@VPN.filter_registry.register('gw-without-ipsec-policies')
class IPSecAlgorithmFilter(Filter):
    """Virtual Networks Gateway Resource IPSec configured

    :example:

    This set of policies will find all Virtual Networks that are not
      configured with a cryptygraphic algorithm.

    .. code-block:: yaml

        policies:
          - name: gateway-configured-with-cryptographic-algorithm
            resource: azure.vnet
            filters:
              - type: configured-with-cryptographic-algorithm
    """

    schema = type_schema('virtual_gateway',required=['state'],
              state={'type': 'string', 'enum': ['Enabled', 'Disabled']})
    schema_alias = False

    def check_state(self, ipsec_policies):
        if self.data.get('state') == 'Disabled' and not ipsec_policies:
            return True
        if self.data.get('state') == 'Enabled' and ipsec_policies:
            return True
        return False

    def process(self, resources, event=None):
      client = self.manager.get_client()
      matched = []
      for vpn in resources:
        if vpn['properties']['gatewayType'] != "ExpressRoute":
          vpnrg = ResourceIdParser.get_resource_group(vpn['id'])
          connections = client.virtual_network_gateway_connections.list(vpnrg)
          for connection in connections:
            if self.check_state(connection.ipsec_policies):
              matched.append(vpn)
      return matched
