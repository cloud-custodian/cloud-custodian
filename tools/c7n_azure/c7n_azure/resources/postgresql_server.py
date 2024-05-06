# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters.core import ValueFilter, ListItemFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.filters import FirewallRulesFilter, FirewallBypassFilter
from netaddr import IPRange, IPSet

AZURE_SERVICES = IPRange('0.0.0.0', '0.0.0.0')  # nosec


@resources.register('postgresql-server')
class PostgresqlServer(ArmResourceManager):
    """PostgreSQL Server Resource

    :example:

    Finds all PostgreSQL Servers that have had zero active connections in the past week

    .. code-block:: yaml

        policies:
          - name: find-all-unused-postgresql-servers
            resource: azure.postgresql-server
            filters:
              - type: metric
                metric: active_connections
                op: eq
                threshold: 0
                timeframe: 168

    :example:

    Finds all PostgreSQL Servers that cost more than 1000 in the last month

    .. code-block:: yaml

        policies:
          - name: find-all-costly-postgresql-servers
            resource: azure.postgresql-server
            filters:
              - type: cost
                key: TheLastMonth
                op: gt
                value: 1000

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.postgresql'
        client = 'PostgreSQLManagementClient'
        enum_spec = ('servers', 'list', None)
        resource_type = 'Microsoft.DBforPostgreSQL/servers'


@PostgresqlServer.filter_registry.register("server-configurations")
class PostgresqlServerConfigurationFilter(ListItemFilter):
    schema = type_schema(
        "server-configurations",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    item_annotation_key = "c7n:ServerConfigurations"
    annotate_items = True

    def get_item_values(self, resource):
        it = self.manager.get_client().configurations.list_by_server(
            resource_group_name=resource["resourceGroup"],
            server_name=resource["name"]
        )
        return [item.serialize(True) for item in it]


@PostgresqlServer.filter_registry.register('security-alert-policies')
class PostgresqlServerSecurityAlertPoliciesFilter(ListItemFilter):
    schema = type_schema(
        "security-alert-policies",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )

    annotate_items = True
    item_annotation_key = "c7n:SecurityAlertPolicies"

    def get_item_values(self, resource):
        it = self.manager.get_client().server_security_alert_policies.list_by_server(
            resource_group_name=resource["resourceGroup"],
            server_name=resource["name"],
        )
        return [item.serialize(True) for item in it]


@PostgresqlServer.filter_registry.register("firewall-bypass")
class PostgresqlServerFirewallBypassFilter(FirewallBypassFilter):
    """
    Filters resources by the firewall bypass rules.

    :example:

    This policy will find all PostgreSQL Servers with enabled Azure Services bypass rules

    .. code-block:: yaml

        policies:
          - name: azure-postgresql-server-firewall-bypass
            resource: azure.postgresql-server
            filters:
              - type: firewall-bypass
                mode: equal
                list:
                    - AzureServices
    """

    schema = FirewallBypassFilter.schema(["AzureServices"])

    def _query_bypass(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource_group_name=resource["resourceGroup"],
            server_name=resource["name"]
        )

        for r in query:
            rule = IPRange(r.start_ip_address, r.end_ip_address)
            if rule == AZURE_SERVICES:
                return ["AzureServices"]
        return []


@PostgresqlServer.filter_registry.register('firewall-rules')
class PostgresqlServerFirewallRulesFilter(FirewallRulesFilter):
    def _query_rules(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])
        resource_rules = IPSet()
        for r in query:
            rule = IPRange(r.start_ip_address, r.end_ip_address)
            if rule == AZURE_SERVICES and not self.data.get('include-azure-services', False):
                # Ignore 0.0.0.0 magic value representing Azure Cloud bypass
                continue
            resource_rules.add(rule)
        return resource_rules


@PostgresqlServer.filter_registry.register('configuration-parameter')
class ConfigurationParametersFilter(ValueFilter):
    """Filter by configuration parameter for this postresql server

    Configurations are made available to the filter as a map with each
    key holding the name of the configuration and each value holding
    the properties of the Configuration as defined here:
    https://learn.microsoft.com/en-us/python/api/azure-mgmt-rdbms/azure.mgmt.rdbms.postgresql.models.configuration?view=azure-python

    :example:

    Example JSON document showing the data format provided to the filter

    .. code-block:: json

      {
        "value": "off",
        "description": "Logs each successful connection.",
        "defaultValue": "on",
        "dataType": "Boolean",
        "allowedValues": "on,off",
        "source": "user-override",
        "isConfigPendingRestart": "False",
        "isDynamicConfig": "True"
      }

    :example:

    Find Postgresql servers with log_connections not enabled

    .. code-block:: yaml

        policies:
          - name: sql-database-no-log-connections
            resource: azure.postgresql-server
            filters:
              - type: configuration-parameter
                name: log_connections
                key: value
                op: ne
                value: 'on'

    """

    schema = type_schema(
        'configuration-parameter',
        required=['type', 'name'],
        rinherit=ValueFilter.schema,
        name=dict(type='string')
    )

    def __call__(self, resource):
        key = f'c7n:config-params:{self.data["name"]}'
        if key not in resource['properties']:
            client = self.manager.get_client()
            query = client.configurations.get(
                resource['resourceGroup'],
                resource['name'],
                self.data["name"]
            )

            resource['properties'][key] = query.serialize(True).get('properties')

        return super().__call__(resource['properties'][key])
