# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('host-pools')
class HostPools(ArmResourceManager):
    """Host Pools Resource

    :example:

    This policy will lists the Desktop Virtualization host pools.

    .. code-block:: yaml

        policies:
          - name: list-host-pools-missing-identity
            resource: azure.host-pools
            filters:
              - type: value
                key: identity
                value: absent

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.desktopvirtualization'
        client = 'DesktopVirtualizationMgmtClient'
        enum_spec = ('host_pools', 'list', None)

        resource_type = 'Microsoft.DesktopVirtualization/hostPools'
