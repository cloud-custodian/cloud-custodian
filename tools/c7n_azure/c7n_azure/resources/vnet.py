# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager


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


@resources.register('subnet')
class Subnet(ChildArmResourceManager):
    """
    Subnet resource

    :example:

    This policy will find all Subnets that do not have a Network Security
    Group associated with them.

    .. code-block:: yaml

        policies:
          - name: find-subnets-without-nsg
            resource: azure.subnet
            filters:
              - type: value
                  key: properties.networkSecurityGroup.id
                  op: equal
                  value: null
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('subnets', 'list', None)
        resource_type = 'Microsoft.Network/virtualNetworks/subnets'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.addressPrefix',
            'properties.networkSecurityGroup.id',
        )
        parent_manager_name = 'vnet'

        @classmethod
        def extra_args(cls, parent_resource):
            # NOTE: these extra args are valid but not actually used.
            # Currently, we can retrieve subnets from parent's JSON. They
            # can also be retrieved from API, but its response has no
            # additional attributes
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'virtual_network_name': parent_resource['name'],
            }

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        return parent_resource['properties'].get('subnets') or []
