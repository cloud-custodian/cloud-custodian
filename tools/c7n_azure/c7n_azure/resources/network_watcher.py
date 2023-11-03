# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('networkwatcher', aliases=['network-watcher'])
class NetworkWatcher(ArmResourceManager):
    """Azure Network Watcher Resource

    :example:

    Returns all enabled Network Watcher

    .. code-block:: yaml

        policies:
          - name: list-all-enabled-network-watcher
            resource: azure.networkwatcher
            filters:
              - type: value
                key: properties.provisioningState
                op: equal
                value: "Succeeded"

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_watchers', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/networkWatchers'
