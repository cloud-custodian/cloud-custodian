# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.core.rest import HttpRequest

from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import DescribeSource, QueryResourceManager

log = logging.getLogger('custodian.azure.cost-management-scheduled-action')

# ScheduledActionsOperations.list_by_scope serializes its `scope` path
# parameter without skip_quote=True (unlike ExportsOperations, whose
# enum_spec-driven listing this resource would otherwise follow), so the
# SDK percent-encodes the '/' characters in 'subscriptions/{id}' and
# produces a malformed request. Confirmed present in azure-mgmt-
# costmanagement 4.0.0, 4.0.1, and 5.0.0 - an upstream SDK bug, not
# specific to this resource. Bypass the typed operation and issue the
# request directly.
SCHEDULED_ACTIONS_API_VERSION = '2022-10-01'


class CostManagementScheduledActionSource(DescribeSource):

    def get_resources(self, query):
        manager = self.manager
        client = manager.get_client()
        subscription_id = manager.get_session().get_subscription_id()

        url = '/subscriptions/{0}/providers/Microsoft.CostManagement/scheduledActions'\
            .format(subscription_id)
        params = {'api-version': SCHEDULED_ACTIONS_API_VERSION}

        resources = []
        while url:
            response = client._send_request(HttpRequest('GET', url, params=params))
            response.raise_for_status()
            data = response.json()
            resources.extend(data.get('value', []))
            url = data.get('nextLink')
            params = None

        return resources


@resources.register('cost-management-scheduled-action')
class CostManagementScheduledAction(QueryResourceManager):
    """ Cost Management Scheduled Actions for current subscription
    (doesn't include Resource Group, Billing Account, or other scopes).

    A scheduled action of kind ``InsightAlert`` is Azure's cost anomaly
    alert: it compares current spend against a baseline Cost Management
    learns from the scope's own history. Other kinds (for example
    ``Email``) mail cost analysis data on a schedule and carry no baseline.

    :example:

    Returns all cost management scheduled actions for current subscription
    scope

    .. code-block:: yaml

        policies:
          - name: get-cost-management-scheduled-actions
            resource: azure.cost-management-scheduled-action

    :example:

    Find anomaly alerts that are disabled, run on a cadence other than
    daily, or carry no notification recipients

    .. code-block:: yaml

        policies:
          - name: find-unhealthy-cost-anomaly-alerts
            resource: azure.cost-management-scheduled-action
            filters:
              - type: value
                key: kind
                value: InsightAlert
              - or:
                - type: value
                  key: properties.status
                  op: ne
                  value: Enabled
                - type: value
                  key: properties.schedule.frequency
                  op: ne
                  value: Daily
                - type: value
                  key: properties.notification.to
                  value: absent
    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Cost']

        service = 'azure.mgmt.costmanagement'
        client = 'CostManagementClient'
        default_report_fields = (
            'name',
            'kind',
            'properties.status',
            'properties.schedule.frequency',
        )
        resource_type = 'Microsoft.CostManagement/scheduledActions'

    def get_source(self, source_type):
        return CostManagementScheduledActionSource(self)


@CostManagementScheduledAction.action_registry.register('update')
class UpdateScheduledAction(AzureBaseAction):
    """Enable a disabled Cost Management scheduled action (for example an
    ``InsightAlert`` anomaly alert).

    ScheduledActionsOperations.create_or_update_by_scope has the same
    upstream SDK bug as list_by_scope (see
    CostManagementScheduledActionSource.get_resources): it serializes its
    `scope` path parameter without skip_quote=True, percent-encoding the
    '/' characters and producing a malformed request. This bypasses the
    typed operation and PUTs directly to the same subscription-scoped URL
    get_resources lists from - resource['id'] isn't used because the API
    doesn't consistently return it with a leading slash.

    :example:

    Enable disabled anomaly alerts

    .. code-block:: yaml

        policies:
          - name: enable-cost-anomaly-alerts
            resource: azure.cost-management-scheduled-action
            filters:
              - type: value
                key: kind
                value: InsightAlert
              - type: value
                key: properties.status
                op: ne
                value: Enabled
            actions:
              - type: update
    """

    schema = type_schema('update')
    permissions = ('Microsoft.CostManagement/scheduledActions/write',)

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.subscription_id = self.manager.get_session().get_subscription_id()

    def _process_resource(self, resource):
        url = (
            '/subscriptions/{0}/providers/Microsoft.CostManagement/scheduledActions/{1}'
            .format(self.subscription_id, resource['name'])
        )
        params = {'api-version': SCHEDULED_ACTIONS_API_VERSION}
        body = {
            'kind': resource['kind'],
            'properties': {**resource['properties'], 'status': 'Enabled'},
        }

        response = self.client._send_request(
            HttpRequest('PUT', url, params=params, json=body))
        response.raise_for_status()
        return 'enabled'
