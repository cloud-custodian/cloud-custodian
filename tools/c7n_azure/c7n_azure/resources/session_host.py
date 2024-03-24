# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser
from c7n.filters import ValueFilter
from c7n.utils import local_session, type_schema


@resources.register('session-host')
class SessionHost(ChildArmResourceManager):
    """Session Host Resource

    :example:

    This policy will lists the Desktop Virtualization session hosts.

    .. code-block:: yaml

        policies:
          - name: list-session-host-disconnected
            resource: azure.session-host
            filters:
              - type: value
                key: status
                value: Disconnected

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.desktopvirtualization'
        client = 'DesktopVirtualizationMgmtClient'
        enum_spec = ('session_hosts', 'list', None)
        parent_manager_name = 'host-pool'

        resource_type = 'Microsoft.DesktopVirtualization/hostPools/sessionHost'

        @classmethod
        def extra_args(cls, parent_resource):
            host_pool_name = parent_resource['name']
            resource_group_name = parent_resource['resourceGroup']

            return {
                'resource_group_name': resource_group_name,
                'host_pool_name': host_pool_name,
                'page_size': None,
                'is_descending': None,
                'initial_skip': None
            }


@SessionHost.filter_registry.register('session-host-vm')
class VMInstanceViewFilter(ValueFilter):
    """Check session host virtual machine

    :example:

    .. code-block:: yaml

        policies:
          - name: test-session-host-is-configured-with-managed-identity
            resource: azure.session-host
            filters:
                - type: session-host-vm
                  key: identity
                  value: absent

    """
    schema = type_schema('session-host-vm',
        rinherit=ValueFilter.schema
    )

    def process(self, resources, event=None):
        self.session = local_session(self.manager.session_factory)
        client = self.session.client("azure.mgmt.compute.ComputeManagementClient")
        matched = []
        for host in resources:
            rg = ResourceIdParser.get_resource_group(host['id'])
            vm = ResourceIdParser.get_resource_name(host['properties']['resourceId'])
            vmachine = client.virtual_machines.get(rg, vm)
            if self.match(vmachine.serialize(True)):
                matched.append(host)
        return matched
