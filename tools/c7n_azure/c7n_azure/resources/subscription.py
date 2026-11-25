# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.resource.policy.models import PolicyAssignment
from azure.mgmt.resource import SubscriptionClient
from azure.mgmt.resource.resources.models import GenericResource

from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters.missing import Missing
from c7n.filters.core import ValueFilter
from c7n.manager import ResourceManager
from c7n.utils import local_session, type_schema

from c7n_azure.actions.diagnostic_settings import SetDiagnosticSettingsAction
from c7n_azure.actions.tagging import Tag, RemoveTag, TagTrim, TagDelayedAction
from c7n_azure.filters import DiagnosticSettingsFilter, TagActionFilter
from c7n_azure.provider import resources
from c7n_azure.query import QueryMeta, TypeInfo


@resources.register('subscription')
class Subscription(ResourceManager, metaclass=QueryMeta):
    """Subscription Resource

    :example:

    This policy creates Azure Policy scoped to the current subscription if doesn't exist.

    .. code-block:: yaml

        policies:
          - name: azure-policy-sample
            resource: azure.subscription
            filters:
              - type: missing
                policy:
                  resource: azure.policyassignments
                  filters:
                    - type: value
                      key: properties.displayName
                      op: eq
                      value_type: normalize
                      value: dn_sample_policy
            actions:
              - type: add-policy
                name: sample_policy
                display_name: dn_sample_policy
                definition_name: "Audit use of classic storage accounts"

    """

    class resource_type(TypeInfo):
        doc_groups = ['Subscription']

        id = 'subscriptionId'
        name = 'displayName'
        filter_name = None
        service = 'subscription'

    def get_model(self):
        return self.resource_type

    def get_session(self):
        """Get the session for this resource manager."""
        return local_session(self.session_factory)

    def resources(self):
        return self.filter_resources([self._get_subscription(self.session_factory, self.config)])

    def get_resources(self, resource_ids):
        return [self._get_subscription(self.session_factory, self.config)]

    def _get_subscription(self, session_factory, config):
        session = local_session(session_factory)
        client = SubscriptionClient(session.get_credentials())
        details = client.subscriptions.get(subscription_id=session.get_subscription_id())
        return details.serialize(True)

    def tag_operation_enabled(self, resource_type):
        """Subscriptions support tagging operations."""
        return True


Subscription.filter_registry.register('missing', Missing)

# Register tagging actions for subscriptions
Subscription.action_registry.register('tag', Tag)
Subscription.action_registry.register('untag', RemoveTag)
Subscription.action_registry.register('tag-trim', TagTrim)
Subscription.action_registry.register('mark-for-op', TagDelayedAction)
Subscription.filter_registry.register('marked-for-op', TagActionFilter)


@Subscription.filter_registry.register('diagnostic-settings')
class SubscriptionDiagnosticSettingFilter(ValueFilter):
    """Filter by diagnostic settings for this subscription

    Each diagnostic setting for the subscription is made available to the filter. The data format
    is the result of making the following Azure API call and extracting the "value" property:
    https://learn.microsoft.com/en-us/rest/api/monitor/subscription-diagnostic-settings/list?tabs=HTTP

    :example:

    Example JSON document showing the data format provided to the filter

    .. code-block:: json
        {
          "id": "...",
          "name": "...",
          "properties": {
            "eventHubAuthorizationRuleId": "...",
            "eventHubName": "...",
            "logs": [
              { "category": "Administrative", "enabled": true },
              { "category": "Security", "enabled": false }
            ],
            "marketplacePartnerId": "...",
            "serviceBusRuleId": "...",
            "storageAccountId": "...",
            "workspaceId": "..."
          },
          "systemData": {}
          "type": "..."
        }

    :example:

    Check if the subscription has Security logs enabled in at least one setting

    .. code-block:: yaml

        policies:
          - name: subscription-security-logs-enabled
            resource: azure.subscription
            filters:
              - not:
                - type: diagnostic-settings
                  key: "properties.logs[?category == 'Security'].enabled[]"
                  op: contains
                  value: true

    """

    cache_key = 'c7n:diagnostic-settings'

    schema = type_schema(
        'diagnostic-settings',
        rinherit=ValueFilter.schema
    )

    def _get_subscription_diagnostic_settings(self, session, subscription_id):
        client = session.client('azure.mgmt.resource.ResourceManagementClient')
        # Kept in the raw shape (properties nested, camelCase), which policies key on.
        settings = DiagnosticSettingsFilter.get_raw_settings(
            client, f"/subscriptions/{subscription_id}")

        # put an empty item in when no diag settings so the absent operator can function
        if not settings:
            settings = [{}]

        return settings

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)

        matched = []
        for resource in resources:
            subscription_id = resource['subscriptionId']

            if self.cache_key in resource:
                settings = resource[self.cache_key]
            else:
                settings = self._get_subscription_diagnostic_settings(
                    session,
                    subscription_id
                )
                resource[self.cache_key] = settings

            filtered_settings = super().process(settings, event=None)

            if filtered_settings:
                matched.append(resource)

        return matched


def _subscription_scope(subscription):
    return f"/subscriptions/{subscription['subscriptionId']}"


@Subscription.action_registry.register('set-diagnostic-settings')
class SubscriptionSetDiagnosticSettings(SetDiagnosticSettingsAction):
    """Create or update a diagnostic setting on the subscription.

    The subscription's diagnostic settings export its activity log. The setting
    called ``name`` is written whole, so an existing setting with that name is
    replaced. Other settings on the subscription are left alone. To turn on
    categories in settings that already exist, use ``update-diagnostic-settings``.

    Set at least one destination (``workspaceId``, ``storageAccountId``, or
    ``eventHubAuthorizationRuleId`` with an optional ``eventHubName``) and
    ``logs``. Each ``logs`` entry names either a ``category``, such as
    ``Administrative`` or ``Security``, or a ``categoryGroup``. Subscription
    settings carry no metrics and have no ``logAnalyticsDestinationType``, so
    neither is accepted here.

    Azure rejects a setting that sends a category to a destination another
    setting on the subscription already sends it to.

    The caller needs ``Microsoft.Insights/diagnosticSettings/write`` on the
    subscription.

    :example:

    Export the activity log to a Log Analytics workspace on any subscription
    that has no diagnostic setting:

    .. code-block:: yaml

       policies:
         - name: subscription-export-activity-log
           resource: azure.subscription
           filters:
             - type: diagnostic-settings
               key: name
               value: absent
           actions:
             - type: set-diagnostic-settings
               name: c7n-activity-log
               workspaceId: >-
                 /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/logging-rg/providers/Microsoft.OperationalInsights/workspaces/security-logs
               logs:
                 - category: Administrative
                   enabled: true
                 - category: Alert
                   enabled: true
                 - category: Policy
                   enabled: true
                 - category: Security
                   enabled: true
    """

    schema = type_schema(
        'set-diagnostic-settings',
        required=['name', 'logs'],
        name=SetDiagnosticSettingsAction.schema['properties']['name'],
        workspaceId={'type': 'string'},
        storageAccountId={'type': 'string'},
        eventHubAuthorizationRuleId={'type': 'string'},
        eventHubName={'type': 'string'},
        logs=SetDiagnosticSettingsAction.schema['properties']['logs'],
    )
    # The schema differs from the ARM resources' one, so it can't share their alias
    schema_alias = False
    permissions = ('Microsoft.Insights/diagnosticSettings/write',)

    PROPERTIES = ('workspaceId', 'storageAccountId', 'eventHubAuthorizationRuleId',
                  'eventHubName', 'logs')

    def _prepare_processing(self):
        # Subscription isn't an ARM resource manager, so it has no get_client.
        # Its id, /subscriptions/{id}, is the scope the parent writes under.
        self.client = self.manager.get_session().client(
            'azure.mgmt.resource.ResourceManagementClient')


@Subscription.action_registry.register('update-diagnostic-settings')
class SubscriptionUpdateDiagnosticSettings(BaseAction):
    """Turn log categories on or off in every diagnostic setting the subscription has.

    Each existing setting is read, the ``logs`` entries are merged into it, and
    the setting is written back. Its destinations, its name, and any log entries
    the policy doesn't name are kept as they were. An entry matches an existing
    one by ``category`` or ``categoryGroup``, ignoring case. An entry with no
    match is added. A setting that already has every entry as requested is not
    written.

    This action doesn't create a setting, so a subscription with none is left
    alone. Use ``set-diagnostic-settings`` for that.

    Azure rejects a setting that sends a category to a destination another
    setting on the subscription already sends it to, so two settings that share
    a destination can't both send the same category. If a write fails, the
    remaining settings are still processed, then the action raises.

    The caller needs ``Microsoft.Insights/diagnosticSettings/read`` and
    ``Microsoft.Insights/diagnosticSettings/write`` on the subscription.

    :example:

    Make every diagnostic setting on the subscription capture the
    Administrative, Alert, Policy and Security categories:

    .. code-block:: yaml

       policies:
         - name: subscription-diagnostic-categories
           resource: azure.subscription
           filters:
             - type: diagnostic-settings
               key: "properties.logs[?enabled].category"
               op: difference
               value_type: swap
               value: [Administrative, Alert, Policy, Security]
           actions:
             - type: update-diagnostic-settings
               logs:
                 - category: Administrative
                   enabled: true
                 - category: Alert
                   enabled: true
                 - category: Policy
                   enabled: true
                 - category: Security
                   enabled: true
    """

    schema = type_schema(
        'update-diagnostic-settings',
        required=['logs'],
        logs={**SetDiagnosticSettingsAction.schema['properties']['logs'], 'minItems': 1},
    )
    permissions = ('Microsoft.Insights/diagnosticSettings/read',
                   'Microsoft.Insights/diagnosticSettings/write')

    def validate(self):
        for entry in self.data['logs']:
            if ('category' in entry) == ('categoryGroup' in entry):
                raise PolicyValidationError(
                    "update-diagnostic-settings: each logs entry needs exactly one of "
                    f"category or categoryGroup, got {entry}")
        return self

    @staticmethod
    def _entry_key(entry):
        if entry.get('category'):
            return ('category', entry['category'].lower())
        return ('categoryGroup', (entry.get('categoryGroup') or '').lower())

    def merge_properties(self, properties):
        """Return ``properties`` with the policy's logs merged in, or None when
        the setting already has every entry as requested.
        """
        # Azure lists the unused one of category/categoryGroup, and unset
        # destinations, as null. Leave nulls out of the write.
        merged = {k: v for k, v in properties.items() if v is not None}
        logs = [{k: v for k, v in entry.items() if v is not None}
                for entry in merged.get('logs') or []]
        changed = False
        for wanted in self.data['logs']:
            key = self._entry_key(wanted)
            existing = next((e for e in logs if self._entry_key(e) == key), None)
            if existing is None:
                logs.append(dict(wanted))
                changed = True
            elif existing.get('enabled') != wanted['enabled']:
                existing['enabled'] = wanted['enabled']
                changed = True
        if not changed:
            return None
        merged['logs'] = logs
        return merged

    def process(self, subscriptions):
        client = self.manager.get_session().client(
            'azure.mgmt.resource.ResourceManagementClient')
        failures = []
        for subscription in subscriptions:
            scope = _subscription_scope(subscription)
            settings = DiagnosticSettingsFilter.get_raw_settings(client, scope)
            if not settings:
                self.log.info("Subscription %s has no diagnostic settings to update",
                              subscription['subscriptionId'])
            for setting in settings:
                properties = self.merge_properties(setting.get('properties') or {})
                if properties is None:
                    continue
                try:
                    # PUT replaces the setting, so the body carries everything it had
                    client.resources.begin_create_or_update_by_id(
                        resource_id=(f"{scope}/providers/Microsoft.Insights"
                                     f"/diagnosticSettings/{setting['name']}"),
                        api_version=DiagnosticSettingsFilter.api_version,
                        parameters=GenericResource(properties=properties),
                    ).result()
                except Exception as e:
                    self.log.error(
                        "Updating diagnostic setting '%s' on subscription %s failed: %s",
                        setting['name'], subscription['subscriptionId'], e, exc_info=True)
                    failures.append(e)
                    continue
                self.log.info("Updated diagnostic setting '%s' on subscription %s",
                              setting['name'], subscription['subscriptionId'])
        if failures:
            raise failures[0]


@Subscription.action_registry.register('add-policy')
class AddPolicy(BaseAction):

    schema = type_schema('add-policy',
        required=['name', 'display_name', 'definition_name'],
        scope={'type': 'string'},
        definition_name={'type': 'string'},
        name={'type': 'string'},
        display_name={'type': 'string'})

    policyDefinitionPrefix = '/providers/Microsoft.Authorization/policyDefinitions/'

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AddPolicy, self).__init__(data, manager, log_dir)

        self.paName = self.data.get('name')
        self.displayName = self.data.get('display_name')

        self.policyDefinitionName = self.data['definition_name']

    def _get_definition_id(self, name):
        return next((r for r in self.policyClient.policy_definitions.list()
                     if name == r.display_name or name == r.id or name == r.name), None)

    def _add_policy(self, subscription):
        parameters = PolicyAssignment(
            display_name=self.displayName,
            policy_definition_id=self.policyDefinition.id)
        self.policyClient.policy_assignments.create(
            scope=self.scope,
            policy_assignment_name=self.paName,
            parameters=parameters
        )

    def process(self, subscriptions):
        self.session = local_session(self.manager.session_factory)
        self.policyClient = self.session.client("azure.mgmt.resource.policy.PolicyClient")

        self.scope = '/subscriptions/' + self.session.subscription_id + \
                     '/' + self.data.get('scope', '')
        self.policyDefinition = self._get_definition_id(self.policyDefinitionName)
        if self.policyDefinition is None:
            raise PolicyValidationError(
                "Azure Policy Definition '%s' not found." % (
                    self.policyDefinitionName))

        for s in subscriptions:
            self._add_policy(s)


@Subscription.action_registry.register('set-activity-log-alert')
class SetActivityLogAlert(BaseAction):
    """Create or update an activity log alert on the subscription.

    The alert watches the subscription's activity log and fires when an event
    matches every entry in ``conditions``. It is identified by ``resource-group``
    and ``name``. If that alert already exists it is replaced as a whole: its tags,
    and any action groups or description the policy doesn't set, are removed.

    - ``name``: the alert's name.
    - ``resource-group``: the resource group to create the alert in. It must
      already exist.
    - ``conditions``: a list of ``field`` and ``equals`` pairs. An event must
      match all of them to fire the alert.
    - ``action-groups``: optional list of action group IDs to notify. Defaults
      to none.
    - ``description``: optional description for the alert.
    - ``enabled``: optional, defaults to ``true``.

    Needs ``Microsoft.Insights/ActivityLogAlerts/Write`` on the resource group.

    :example:

    Create an alert for network security group writes on any subscription that
    doesn't have one:

    .. code-block:: yaml

        policies:
          - name: azure-subscription-nsg-write-alert
            resource: azure.subscription
            filters:
              - type: missing
                policy:
                  resource: azure.alert-logs
                  filters:
                    - type: value
                      key: "properties.condition.allOf[].join('=', [field, equals]) | sort(@)"
                      op: eq
                      value:
                        - category=Administrative
                        - operationName=Microsoft.Network/networkSecurityGroups/write
            actions:
              - type: set-activity-log-alert
                name: nsg-write-alert
                resource-group: my-alerts-rg
                conditions:
                  - field: category
                    equals: Administrative
                  - field: operationName
                    equals: Microsoft.Network/networkSecurityGroups/write
    """

    schema = type_schema(
        'set-activity-log-alert',
        required=['name', 'resource-group', 'conditions'],
        name={'type': 'string', 'minLength': 1, 'maxLength': 260},
        conditions={
            'type': 'array',
            'minItems': 1,
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['field', 'equals'],
                'properties': {
                    'field': {'type': 'string', 'minLength': 1},
                    'equals': {'type': 'string', 'minLength': 1},
                },
            },
        },
        description={'type': 'string'},
        enabled={'type': 'boolean'},
        **{
            'resource-group': {'type': 'string', 'minLength': 1, 'maxLength': 90},
            'action-groups': {
                'type': 'array',
                'uniqueItems': True,
                'items': {'type': 'string', 'minLength': 1},
            },
        }
    )

    def alert_body(self, subscription):
        """Return the request body that creates the alert on ``subscription``."""
        properties = {
            'scopes': [subscription['id']],
            'condition': {'allOf': self.data['conditions']},
            'actions': {'actionGroups': [
                {'actionGroupId': group_id}
                for group_id in self.data.get('action-groups', [])
            ]},
            'enabled': self.data.get('enabled', True),
        }
        if 'description' in self.data:
            properties['description'] = self.data['description']
        # The REST API's own request shape, so the body doesn't depend on the
        # SDK reshaping a flattened dict.
        return {'location': 'Global', 'properties': properties}

    def process(self, subscriptions):
        client = self.manager.get_session().client(
            'azure.mgmt.monitor.MonitorManagementClient')

        for s in subscriptions:
            # Positional on purpose: the body parameter's name differs between
            # azure-mgmt-monitor major versions.
            client.activity_log_alerts.create_or_update(
                self.data['resource-group'], self.data['name'], self.alert_body(s))
            self.log.info(
                "Set activity log alert %s in resource group %s on subscription %s",
                self.data['name'], self.data['resource-group'], s['subscriptionId'])
