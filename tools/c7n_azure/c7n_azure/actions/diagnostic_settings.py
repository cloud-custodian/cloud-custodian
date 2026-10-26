# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.resource.resources.models import GenericResource
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import DiagnosticSettingsFilter

from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema


class SetDiagnosticSettingsAction(AzureBaseAction):
    """
    Create or update an Azure Monitor diagnostic setting on a resource.

    The setting called ``name`` is written whole, so an existing setting with
    that name is replaced. Other settings on the resource are left alone.

    Set at least one destination (``workspaceId``, ``storageAccountId``, or
    ``eventHubAuthorizationRuleId`` with an optional ``eventHubName``) and at
    least one of ``logs`` or ``metrics``. Each ``logs`` entry names either a
    ``category`` or a ``categoryGroup`` such as ``allLogs``. Keys use Azure's
    API casing, so the filter's ``category_group`` is ``categoryGroup`` here.
    ``logAnalyticsDestinationType: Dedicated`` sends to resource-specific
    tables. ``retentionPolicy`` isn't accepted, since Azure stopped honouring
    it in September 2025.

    Azure rejects a setting that sends a category to a destination another
    setting on the resource already sends it to. If a write fails, the
    remaining resources are still processed, then the action raises.

    The caller needs ``Microsoft.Insights/diagnosticSettings/write`` on the
    resource. Storage account and Event Hub destinations also need permission
    to list their keys.

    :example:

    Send HTTP logs to a Log Analytics workspace for web apps that don't
    already send them anywhere. On a web app both the ``audit`` and
    ``allLogs`` groups include AppServiceHTTPLogs, so either one counts:

    .. code-block:: yaml

       policies:
         - name: webapp-enable-http-logs
           resource: azure.webapp
           filters:
             - not:
               - type: diagnostic-settings
                 key: >-
                   logs[?(category == 'AppServiceHTTPLogs' || category_group == 'audit'
                   || category_group == 'allLogs') && enabled]
                 value: not-null
           actions:
             - type: set-diagnostic-settings
               name: c7n-http-logs
               workspaceId: >-
                 /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/logging-rg/providers/Microsoft.OperationalInsights/workspaces/security-logs
               logs:
                 - category: AppServiceHTTPLogs
                   enabled: true
    """

    schema = type_schema(
        'set-diagnostic-settings',
        required=['name'],
        # The name ends the request URL, so it can't contain URL delimiters
        name={'type': 'string', 'minLength': 1, 'pattern': '^[^/?#]+$'},
        workspaceId={'type': 'string'},
        storageAccountId={'type': 'string'},
        eventHubAuthorizationRuleId={'type': 'string'},
        eventHubName={'type': 'string'},
        logAnalyticsDestinationType={'type': 'string'},
        logs={
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['enabled'],
                'properties': {
                    'category': {'type': 'string', 'minLength': 1},
                    'categoryGroup': {'type': 'string', 'minLength': 1},
                    'enabled': {'type': 'boolean'},
                },
            },
        },
        metrics={
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['category', 'enabled'],
                'properties': {
                    'category': {'type': 'string', 'minLength': 1},
                    'enabled': {'type': 'boolean'},
                },
            },
        },
    )
    schema_alias = True

    # Policy fields that are sent to Azure unchanged as the setting's properties
    PROPERTIES = ('workspaceId', 'storageAccountId', 'eventHubAuthorizationRuleId',
                  'eventHubName', 'logAnalyticsDestinationType', 'logs', 'metrics')

    def validate(self):
        destinations = ('workspaceId', 'storageAccountId', 'eventHubAuthorizationRuleId')
        if not any(self.data.get(d) for d in destinations):
            raise PolicyValidationError(
                "set-diagnostic-settings needs a destination: "
                "workspaceId, storageAccountId or eventHubAuthorizationRuleId"
            )

        if self.data.get('eventHubName') and not self.data.get('eventHubAuthorizationRuleId'):
            raise PolicyValidationError(
                "set-diagnostic-settings: eventHubName needs eventHubAuthorizationRuleId"
            )

        if not self.data.get('logs') and not self.data.get('metrics'):
            raise PolicyValidationError(
                "set-diagnostic-settings needs logs or metrics to send"
            )

        for entry in self.data.get('logs', []):
            if ('category' in entry) == ('categoryGroup' in entry):
                raise PolicyValidationError(
                    "set-diagnostic-settings: each logs entry needs exactly one of "
                    "category or categoryGroup, got {}".format(entry)
                )

        return self

    def _process_resources(self, resources, event):
        # The base class logs and swallows errors outside pytest, so a failed write
        # would leave the run looking successful. Set the rest, then raise.
        self._prepare_processing()
        failures = []
        for resource in resources:
            try:
                self._log_modified_resource(resource, self._process_resource(resource))
            except Exception as e:
                self.log.error(
                    "Setting diagnostic setting '%s' on '%s' in resource group '%s' failed: %s",
                    self.data['name'], resource.get('name'), resource.get('resourceGroup'), e,
                    exc_info=True, extra=self._get_action_log_metadata(resource))
                failures.append(e)
        if failures:
            raise failures[0]

    def _prepare_processing(self):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        setting_id = '{}/providers/Microsoft.Insights/diagnosticSettings/{}'.format(
            resource['id'], self.data['name'])
        body = {k: self.data[k] for k in self.PROPERTIES if k in self.data}

        # Not the monitor SDK: 7.0 has no diagnostic settings, and older releases can't
        # send categoryGroup. Write the setting as a generic resource at the filter's
        # api-version. Arguments are named because azure-mgmt-resource 26 reorders them
        # and makes api_version keyword-only.
        self.client.resources.begin_create_or_update_by_id(
            resource_id=setting_id,
            api_version=DiagnosticSettingsFilter.api_version,
            parameters=GenericResource(properties=body),
        ).result()

        return "Set diagnostic setting '{}'".format(self.data['name'])
