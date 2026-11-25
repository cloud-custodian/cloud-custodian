# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.resource.policy.models import PolicyAssignment
from azure.mgmt.resource import SubscriptionClient

from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters.missing import Missing
from c7n.filters.core import ValueFilter
from c7n.manager import ResourceManager
from c7n.utils import local_session, type_schema

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


@Subscription.action_registry.register('create-bastion-host')
class CreateBastionHost(BaseAction):
    """Create or update an Azure Bastion host in the subscription.

    Runs against the subscription rather than an ``azure.bastion-host``, so it
    can remediate a subscription that has no Bastion host at all. The host is
    identified by ``resource-group`` and ``name``. If that host already exists
    it is replaced as a whole: its tags, scale units, and any other settings
    the policy doesn't set go back to their Azure defaults.

    - ``name``: the Bastion host's name.
    - ``resource-group``: the resource group for the host, and for any network
      resources the action creates. It must already exist.
    - ``location``: the Azure region. It must match the virtual network's.
    - ``subnet-id``: an existing ``AzureBastionSubnet`` to put the host in.
    - ``virtual-network``: in place of ``subnet-id``, a virtual network in
      ``resource-group`` to put the host in. If no network with that ``name``
      exists, the action creates one with ``address-prefixes`` and an
      ``AzureBastionSubnet`` of ``subnet-prefix``. If the network exists but
      has no ``AzureBastionSubnet``, the action adds one of ``subnet-prefix``
      and leaves the network's other subnets alone. An existing network or
      subnet is used as it is.
    - ``public-ip-address-id``: optional, an existing ``Standard`` SKU public
      IP address with static allocation. Without it, the action uses the
      public IP address ``<name>-pip`` in ``resource-group``, creating it if
      it doesn't exist.
    - ``sku``: optional, ``name`` is one of ``Basic``, ``Standard`` or
      ``Premium``. Azure defaults to ``Standard``.
    - ``scale-units``: optional, from 2 to 50. Not allowed with the ``Basic``
      SKU, which is fixed at 2.
    - ``tags``: optional tags for the host, and for any network resources the
      action creates.

    The host can only reach virtual machines in its own virtual network, or in
    networks peered to it, so pick the network the virtual machines are in.
    ``AzureBastionSubnet`` must be ``/26`` or larger and hold nothing else.

    The action waits for Azure to finish provisioning the host, which can take
    several minutes.

    Needs ``Microsoft.Network/bastionHosts/write`` on the resource group, plus
    ``Microsoft.Network/virtualNetworks/subnets/join/action`` on the subnet and
    ``Microsoft.Network/publicIPAddresses/join/action`` on the public IP address.
    Creating network resources also needs ``Microsoft.Network/virtualNetworks/write``,
    ``Microsoft.Network/virtualNetworks/subnets/write`` or
    ``Microsoft.Network/publicIPAddresses/write``.

    :example:

    Create a Bastion host, and the network for it, on any subscription that
    doesn't have one:

    .. code-block:: yaml

        policies:
          - name: azure-create-bastion-host-if-missing
            resource: azure.subscription
            filters:
              - type: missing
                policy:
                  resource: azure.bastion-host
            actions:
              - type: create-bastion-host
                name: example-bastion
                resource-group: example-network-rg
                location: eastus
                virtual-network:
                  name: example-vnet
                  address-prefixes:
                    - 10.10.0.0/16
                  subnet-prefix: 10.10.0.0/26
                sku:
                  name: Standard
                scale-units: 2
                tags:
                  managed-by: cloud-custodian
    """

    subnet_name = 'AzureBastionSubnet'

    schema = type_schema(
        'create-bastion-host',
        required=['name', 'resource-group', 'location'],
        # 76 leaves room for the "-pip" suffix within Azure's 80-character limit.
        name={'type': 'string', 'minLength': 1, 'maxLength': 76},
        location={'type': 'string', 'minLength': 1},
        sku={
            'type': 'object',
            'additionalProperties': False,
            'required': ['name'],
            'properties': {
                'name': {'enum': ['Basic', 'Standard', 'Premium']},
            },
        },
        tags={'type': 'object', 'additionalProperties': {'type': 'string'}},
        **{
            'resource-group': {'type': 'string', 'minLength': 1, 'maxLength': 90},
            'subnet-id': {'type': 'string', 'minLength': 1},
            'virtual-network': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['name', 'address-prefixes', 'subnet-prefix'],
                'properties': {
                    'name': {'type': 'string', 'minLength': 1, 'maxLength': 64},
                    'address-prefixes': {
                        'type': 'array',
                        'minItems': 1,
                        'items': {'type': 'string', 'minLength': 1},
                    },
                    'subnet-prefix': {'type': 'string', 'minLength': 1},
                },
            },
            'public-ip-address-id': {'type': 'string', 'minLength': 1},
            'scale-units': {'type': 'integer', 'minimum': 2, 'maximum': 50},
        }
    )

    def validate(self):
        policy = self.manager.data['name']
        if ('subnet-id' in self.data) == ('virtual-network' in self.data):
            raise PolicyValidationError(
                f"{self.type}: set exactly one of subnet-id or virtual-network "
                f"on policy {policy}")
        # Azure only rejects this at the Bastion PUT, after the network
        # resources have been created.
        if 'scale-units' in self.data and self.data.get('sku', {}).get('name') == 'Basic':
            raise PolicyValidationError(
                f"{self.type}: scale-units can't be set with the Basic sku "
                f"on policy {policy}")
        return self

    # The bodies below follow the REST API's request shape:
    # https://learn.microsoft.com/en-us/rest/api/virtualnetwork/

    def _tagged(self, body):
        if 'tags' in self.data:
            body['tags'] = self.data['tags']
        return body

    def virtual_network_body(self):
        """Return the request body that creates the virtual network."""
        network = self.data['virtual-network']
        return self._tagged({
            'location': self.data['location'],
            'properties': {
                'addressSpace': {'addressPrefixes': network['address-prefixes']},
                'subnets': [{
                    'name': self.subnet_name,
                    'properties': {'addressPrefix': network['subnet-prefix']},
                }],
            },
        })

    def subnet_body(self):
        """Return the request body that adds AzureBastionSubnet to a network."""
        return {'properties': {'addressPrefix': self.data['virtual-network']['subnet-prefix']}}

    def public_ip_body(self):
        """Return the request body that creates the public IP address."""
        return self._tagged({
            'location': self.data['location'],
            'sku': {'name': 'Standard'},
            'properties': {'publicIPAllocationMethod': 'Static'},
        })

    def bastion_body(self, subnet_id, public_ip_id):
        """Return the request body that creates the Bastion host."""
        properties = {
            'ipConfigurations': [{
                'name': 'IpConf',
                'properties': {
                    'subnet': {'id': subnet_id},
                    'publicIPAddress': {'id': public_ip_id},
                },
            }],
        }
        if 'scale-units' in self.data:
            properties['scaleUnits'] = self.data['scale-units']
        body = {'location': self.data['location'], 'properties': properties}
        if 'sku' in self.data:
            body['sku'] = {'name': self.data['sku']['name']}
        return self._tagged(body)

    def _subnet_id(self, client):
        if 'subnet-id' in self.data:
            return self.data['subnet-id']

        group = self.data['resource-group']
        network_name = self.data['virtual-network']['name']
        try:
            network = client.virtual_networks.get(group, network_name)
        except ResourceNotFoundError:
            network = client.virtual_networks.begin_create_or_update(
                group, network_name, self.virtual_network_body()).result()
            self.log.info(f"Created virtual network {network_name} in resource group {group}")

        subnet = next((s for s in network.subnets or [] if s.name == self.subnet_name), None)
        if subnet is None:
            # A PUT on the subnet alone, so the network's other subnets are untouched.
            subnet = client.subnets.begin_create_or_update(
                group, network_name, self.subnet_name, self.subnet_body()).result()
            self.log.info(f"Created subnet {self.subnet_name} in virtual network {network_name}")
        return subnet.id

    def _public_ip_id(self, client):
        if 'public-ip-address-id' in self.data:
            return self.data['public-ip-address-id']

        group = self.data['resource-group']
        name = f"{self.data['name']}-pip"
        try:
            public_ip = client.public_ip_addresses.get(group, name)
        except ResourceNotFoundError:
            public_ip = client.public_ip_addresses.begin_create_or_update(
                group, name, self.public_ip_body()).result()
            self.log.info(f"Created public IP address {name} in resource group {group}")
        return public_ip.id

    def process(self, subscriptions):
        client = self.manager.get_session().client(
            'azure.mgmt.network.NetworkManagementClient')

        for s in subscriptions:
            body = self.bastion_body(self._subnet_id(client), self._public_ip_id(client))
            client.bastion_hosts.begin_create_or_update(
                self.data['resource-group'], self.data['name'], body).result()
            self.log.info(
                f"Created Bastion host {self.data['name']} in resource group "
                f"{self.data['resource-group']} on subscription {s['subscriptionId']}")
