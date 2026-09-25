# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from msrestazure.tools import parse_resource_id

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import FlowLogsFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


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


@Vnet.filter_registry.register('flow-logs')
class FlowLogs(FlowLogsFilter):
    """Filter a Virtual Network by its associated (virtual network) flow logs.

    :example:

    Find all virtual networks with no flow logs configured, or with a flow-log
    retention less than 90 days. A retention of 0 days means logs are retained
    indefinitely and is treated as compliant (CIS Azure Foundations 8.8).

    .. code-block:: yaml

        policies:
          - name: vnet-flow-log-retention-below-90-days
            resource: azure.vnet
            filters:
              - or:
                - type: flow-logs
                  key: logs
                  value: empty
                - and:
                  - type: flow-logs
                    key: logs[0].retentionPolicy.days
                    op: ne
                    value: 0
                  - type: flow-logs
                    key: logs[0].retentionPolicy.days
                    op: lt
                    value: 90
    """


@Vnet.action_registry.register('set-flow-log')
class SetFlowLog(AzureBaseAction):
    """Update the (virtual network) flow log already configured on a Virtual Network.

    This only edits an existing flow log (e.g. its retention or enabled state); it
    does not create one for a vnet that has none. ``storage-account``, if given,
    moves the flow log to a different storage account; otherwise the existing one
    is left as-is. A vnet with no existing flow log raises a ``PolicyExecutionError``
    rather than silently creating one, since choosing a storage account and Network
    Watcher for a brand-new flow log requires a decision this action doesn't make.

    :example:

    Bring vnets found by the ``flow-logs`` filter into compliance with a 90-day
    retention (CIS Azure Foundations 8.8).

    .. code-block:: yaml

        policies:
          - name: enable-vnet-flow-log-retention
            resource: azure.vnet
            filters:
              - and:
                - type: flow-logs
                  key: logs[0].retentionPolicy.days
                  op: ne
                  value: 0
                - type: flow-logs
                  key: logs[0].retentionPolicy.days
                  op: lt
                  value: 90
            actions:
              - type: set-flow-log
                enabled: true
                retention: 90
    """

    schema = type_schema(
        'set-flow-log',
        **{
            'storage-account': {'type': 'string'},
            'enabled': {'type': 'boolean'},
            'retention': {'type': 'integer', 'minimum': 0},
        }
    )

    def validate(self):
        storage_account = self.data.get('storage-account')
        if storage_account and not storage_account.startswith('/subscriptions/'):
            raise PolicyValidationError(
                "set-flow-log storage-account must be a full resource id, "
                "got: %s" % storage_account)

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        existing_logs = resource['properties'].get('flowLogs', [])
        if not existing_logs:
            raise PolicyExecutionError(
                "set-flow-log only updates an existing flow log; '%s' has none"
                % resource['name'])

        parsed_id = parse_resource_id(existing_logs[0]['id'])
        watcher_rg = parsed_id['resource_group']
        watcher_name = parsed_id['name']
        flow_log_name = parsed_id['resource_name']

        existing_flow_log = None
        if 'storage-account' not in self.data or 'enabled' not in self.data \
                or 'retention' not in self.data:
            existing_flow_log = self.client.flow_logs.get(
                watcher_rg, watcher_name, flow_log_name
            )

        storage_id = self.data.get('storage-account')
        if not storage_id:
            storage_id = existing_flow_log.storage_id

        params = {
            'location': resource['location'],
            'target_resource_id': resource['id'],
            'storage_id': storage_id,
            'enabled': self.data.get('enabled', existing_flow_log
                                      and existing_flow_log.enabled),
        }

        if 'retention' in self.data:
            retention = self.data['retention']
            params['retention_policy'] = {
                'days': retention,
                'enabled': retention != 0,
            }
        elif existing_flow_log and existing_flow_log.retention_policy:
            params['retention_policy'] = existing_flow_log.retention_policy

        self.client.flow_logs.begin_create_or_update(
            watcher_rg, watcher_name, flow_log_name, params
        ).result()

        return "flow log '%s' updated on network watcher '%s'" % (flow_log_name, watcher_name)
