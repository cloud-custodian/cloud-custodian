# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters.core import ValueFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.filters import FirewallRulesFilter
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


@PostgresqlServer.filter_registry.register('firewall-rules')
class PostgresqlServerFirewallRulesFilter(FirewallRulesFilter):
    def _query_rules(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])
        resource_rules = IPSet()
        for r in query:
            rule = IPRange(r.start_ip_address, r.end_ip_address)
            if rule == AZURE_SERVICES:
                # Ignore 0.0.0.0 magic value representing Azure Cloud bypass
                continue
            resource_rules.add(rule)
        return resource_rules


@PostgresqlServer.filter_registry.register('configuration-parameters')
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
        log_connections: {
          "id": "<example-id>",
          "name": "log_connections",
          "type": "Microsoft.DBforPostgreSQL/servers/configurations",
          "value": "off",
          "description": "Logs each successful connection.",
          "default_value": "on",
          "data_type": "Boolean",
          "allowed_values": "on,off",
          "source": "user-override"
        },
        {
          "id": "<example-id>",
          "name": "log_min_duration_statement",
          "type": "Microsoft.DBforPostgreSQL/servers/configurations",
          "value": "-1",
          "description": "example description",
          "default_value": "-1",
          "data_type": "Integer",
          "allowed_values": "-1-2147483647",
          "source": "system-default"
        }
      }

    :example:

    Find Postgresql servers with log_connections not enabled

    .. code-block:: yaml

        policies:
          - name: sql-database-no-log-connections
            resource: azure.postgresql-server
            filters:
              - type: configuration-parameters
                key: log_connections.value
                op: ne
                value: 'on'

    """
    schema = type_schema('configuration-parameters', rinherit=ValueFilter.schema)

    def __call__(self, resource):
        key = 'configurations'
        if key not in resource['properties']:
            client = self.manager.get_client()
            query = client.configurations.list_by_server(
                resource['resourceGroup'],
                resource['name']
            )

            # map the config parameters to an dict to make validating individual values easier
            configurations = {item.name: vars(item) for item in query or []}
            resource['properties'][key] = configurations

        return super(ConfigurationParametersFilter, self).__call__(resource['properties'][key])
