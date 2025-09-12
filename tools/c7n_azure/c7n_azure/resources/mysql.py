# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.utils import type_schema
from c7n.filters.core import ValueFilter
from c7n_azure.filters import scalar_ops


@resources.register('mysql')
class MySQL(ArmResourceManager):
    """Azure MySQL Server Resource

    :example:

    Returns all MySQL servers

    .. code-block:: yaml

        policies:
          - name: basic-logic-app
            resource: azure.mysql
            filters:
              - type: value
                key: sku.name
                op: equal
                value: Basic

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.mysql'
        client = 'MySQLManagementClient'
        enum_spec = ('servers', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.DBForMySQL/servers'


@MySQL.filter_registry.register('server-configuration')
class ServerConfigurationsFilter(ValueFilter):
    """Filter by server parameter for this MySql server

    Configurations are made available to the filter as a map with each
    key holding the name of the configuration and each value holding
    the properties of the Configuration as defined here:
    https://learn.microsoft.com/en-us/python/api/azure-mgmt-rdbms/azure.mgmt.rdbms.mysql.models.configuration?view=azure-python

    :example:

    Example JSON document showing the data format provided to the filter

    .. code-block:: json

      {
       "value": "OFF",
        "description": "Allow to audit the log.",
        "defaultValue": "OFF",
        "dataType": "Enumeration",
        "allowedValues": "ON,OFF",
        "source": "system-default",
        "isConfigPendingRestart": "False",
        "isDynamicConfig": "True",
        "isReadOnly": "False"
      }

    :example:

    Find Mysql servers with audit_not_enabled not equal to "ON"

    .. code-block:: yaml

        policies:
          - name: mysql-server-audit-log-enabled
            resource: azure.mysql
            filters:
              - type: server-configuration
                name: audit_not_enabled
                key: value
                op: ne
                value: 'ON'

    """

    schema = type_schema(
        'server-configuration',
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


@MySQL.filter_registry.register('security-alert-policy')
class MySqlServerSecurityAlertPoliciesFilter(ValueFilter):

    schema = type_schema('security-alert-policy',
                         rinherit=ValueFilter.schema)

    def _perform_op(self, a, b):
        op = scalar_ops.get(self.data.get('op', 'eq'))
        return op(a, b)

    def process(self, resources, event=None):
        client = self.manager.get_client('azure.mgmt.rdbms.mysql.MySQLManagementClient')
        filtered_resources = []

        for resource in resources:
            if resource['sku']['tier'] == 'Basic':
                continue
            alert = client.server_security_alert_policies.get(
                server_name=resource['name'],
                resource_group_name=resource['resourceGroup'],
                security_alert_policy_name='Default')
            attribute = getattr(alert, self.data.get('key'))
            if self._perform_op(attribute, self.data.get('value')):
                filtered_resources.append(resource)
                break

        return filtered_resources
