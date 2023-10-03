# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('host-pool')
class HostPool(ArmResourceManager):
    """Host Pool Resource

    :example:

    This policy will lists the Desktop Virtualization host pools.

    .. code-block:: yaml

        policies:
          - name: list-host-pool-missing-identity
            resource: azure.host-pool
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
