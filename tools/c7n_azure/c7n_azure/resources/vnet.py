# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import ValueFilter, Filter
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


@Vnet.filter_registry.register('subnet-application-gateway')
class SubnetApplicationGatewayVnetFilter(ValueFilter):

    schema = type_schema('subnet-application-gateway')

    def process(self, resources, event=None):
        client = self.manager.get_client()
        self.application_gateways = client.application_gateways.list_all()
        filtered_resources = []
        for vnet in resources:
            for subnet_id in vnet['properties']['subnets']:
                if self._mapping_resources(subnet_id['id']):
                    filtered_resources.append(vnet)
                    break
        return filtered_resources

    def _mapping_resources(self, subnet_id):
        for application_gateway in self.application_gateways:
            for subnet in application_gateway.gateway_ip_configurations:
                if subnet.subnet.id == subnet_id:
                    return True
        return False


@Vnet.filter_registry.register('network-interface-assignment')
class NetworkInterfaceAssignmentFilter(Filter):
    """
    Filters resources by network interface assignments.

    Available values:
    - present (checks if a field is present),
    - absent (checks if a field is absent),
    - not-null (checks if a field is not null),
    - empty (checks if a field is empty),
    - regular value (compare with a value)

    :example:

    .. code-block:: yaml

        policies:
          - name: vnet-network-interface-assignment-filter
            resource: azure.vnet
            filters:
              - type: network-interface-assignment
                key: virtual_machine
                value: present
    """

    schema = type_schema(
        'network-interface-assignment', rinherit=ValueFilter.schema
    )

    def __call__(self, resource):
        return resource

    @staticmethod
    def __network_interfaces_to_map(network_interfaces):
        network_interfaces_map = {}
        for network_interface in network_interfaces:
            network_interface_dict = network_interface.as_dict()
            ip_configurations = network_interface_dict.get("ip_configurations")
            for ip_configuration in ip_configurations:
                if ip_configuration.get("primary"):
                    network_interfaces_map[ip_configuration.get("id")] = network_interface_dict
                    break
        return network_interfaces_map

    @staticmethod
    def __match(object_value, data_value):
        if object_value is None and data_value == 'absent':
            return True
        elif object_value is not None and data_value == 'present':
            return True
        elif data_value == 'not-null' and object_value:
            return True
        elif data_value == 'empty' and not object_value:
            return True
        elif object_value == data_value:
            return True

        return False

    def __data_value_matches_value_in_network_interface(
            self, ip_configurations, network_interfaces_map, data_key, data_value):
        valid = False
        for ip_configuration in ip_configurations:
            ip_configuration_id = ip_configuration.get("id")
            if ip_configuration_id is not None:
                network_interface = network_interfaces_map.get(ip_configuration_id)
                if network_interface is not None:
                    object_value = network_interface.get(data_key)
                    if self.__match(object_value, data_value):
                        valid = True
                        break
        return valid

    def process(self, resources, event=None):
        client = self.manager.get_client('azure.mgmt.network.NetworkManagementClient')

        filtered_resources = []
        data_key = self.data['key']
        data_value = self.data['value']

        network_interfaces = client.network_interfaces.list_all()
        network_interfaces_map = self.__network_interfaces_to_map(network_interfaces)

        for resource in resources:
            subnets = resource.get("properties").get("subnets", [])
            for subnet in subnets:
                ip_configurations = subnet.get("properties").get("ipConfigurations", [])
                add_to_filtered = self.__data_value_matches_value_in_network_interface(
                    ip_configurations, network_interfaces_map, data_key, data_value)
                if add_to_filtered:
                    filtered_resources.append(resource)

        return super(NetworkInterfaceAssignmentFilter, self).process(
            filtered_resources, event)
