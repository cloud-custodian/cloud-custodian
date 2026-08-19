# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import ListItemFilter
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
        resource_type = 'Microsoft.Network/virtualNetworks'


@Vnet.filter_registry.register('network-interface')
class NetworkInterfaceFilter(ListItemFilter):
    """
    Filter Virtual networks by their network interaces

    :example:

    .. code-block:: yaml

        policies:
          - name: vnet-network-interfaces
            resource: azure.vnet
            filters:
              - type: network-interface
                attrs:
                  - type: value
                    key: properties.virtualMachine
                    value: present
    """

    schema = type_schema(
        'network-interface',
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotation_key = 'c7n:NetworkInterfaces'

    def __init__(self, data, manager=None):
        data['key'] = f'"{self.annotation_key}"'
        super().__init__(data, manager)

    @staticmethod
    def _get_primary_subnet_id(interface):
        for conf in interface['properties']['ipConfigurations']:
            if conf.get('properties', {}).get('primary'):
                return conf['properties']['subnet']['id']
        # should never reach

    @staticmethod
    def _vnet_id_from_subnet_id(subnet_id):
        """
        Extracts vnet id from subnet id:
        """
        return subnet_id.rsplit('/', maxsplit=2)[0]

    def process(self, resources, event=None):
        vnet_id_to_interfaces = {}
        for interface in self.manager.get_resource_manager('azure.networkinterface').resources():
            vnet_id = self._vnet_id_from_subnet_id(
                self._get_primary_subnet_id(interface)
            )
            vnet_id_to_interfaces.setdefault(vnet_id, []).append(interface)

        for r in resources:
            r[self.annotation_key] = vnet_id_to_interfaces.get(r['id'], [])
        return super().process(resources, event)
