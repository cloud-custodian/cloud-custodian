# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ResourceIdParser
from c7n.filters.core import ValueFilter
from c7n.utils import type_schema

@resources.register('vnet')
class Vnet(ArmResourceManager):
    """Virtual Networks Resource

    :example:

    This set of policies will find all Virtual Networks that do not have DDOS protection enabled.

    .. code-block:: yaml

        policies:
          - name: find-vnets-ddos-protection-disabled
            resource: azure.vnet
            filters:
              - type: value
                key: properties.enableDdosProtection
                op: equal
                value: False

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('virtual_networks', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/virtualNetworks'

@Vnet.filter_registry.register('gw-without-ipsec-policies')
class IPSecAlgorithmFilter(ValueFilter):
    """Virtual Networks Gateway Resource IPSec configured

    :example:

    This set of policies will find all Virtual Networks that are not
      configured with a cryptygraphic algorithm.

    .. code-block:: yaml

        policies:
          - name: gateway-configured-with-cryptographic-algorithm
            resource: azure.vnet
            filters: 
              - type: configured-with-cryptographic-algorithm,
    """
    schema = type_schema('virtual_gateway', rinherit=ValueFilter.schema)
    schema_alias = False
      
    def process(self, resources, event=None):
      client = self.manager.get_client()
      matched = []
      for resource in resources:
          rg = ResourceIdParser.get_resource_group(resource["id"])
          vpns = client.virtual_network_gateways.list(rg)
          for vpn in vpns:
              if vpn.gateway_type != "ExpressRoute":
                vpnrg = ResourceIdParser.get_resource_group(vpn.id)
                connections = client.virtual_network_gateway_connections.list(
                  vpnrg
                )
                for connection in connections:
                  if not connection.ipsec_policies:
                      matched.append(resource)
      return matched

