# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.utils import type_schema
from c7n.filters.core import ValueFilter


@resources.register('mysql-flexibleserver')
class MySQLFlexibleServer(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.mysql_flexibleservers'
        client = 'MySQLManagementClient'
        enum_spec = ('servers', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.DBForMySQL/flexibleservers/configurations'


@MySQLFlexibleServer.filter_registry.register('server-parameter')
class ServerParametersFilter(ValueFilter):
    """Filter by configuration parameter for mysql flexible server

    :example:

    Example JSON document showing the data format provided to the filter

    .. code-block:: json

      {
        "value": "TLSv1.2"
        "description": "Which protocols the server permits for encrypted
        connections. By default, TLS 1.2 is enforced",
        "defaultValue": "TLSv1.2",
        "dataType": "Set",
        "allowedValues": "TLSv1,TLSv1.1,TLSv1.2",
        "source": "system-default",
        "isReadOnly": "False",
        "isConfigPendingRestart": "False",
        "isDynamicConfig": "False",
      }

    :example:

    Find Mysql Flexible servers with tls_version not set to TLSV1.2

    .. code-block:: yaml

        policies:
          - name: mysql-flexible-server-tls-version
            resource: azure.mysql-flexibleserver
            filters:
              - type: server-parameter
                name: tls_version
                key: value
                op: eq
                value: 'TLSv1.2'

    """

    schema = type_schema(
        'server-parameter',
        required=['type', 'name'],
        rinherit=ValueFilter.schema,
        name={
            'type': 'string',
            'allowed_value': ['TLSv1.2']
        },
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

        return super().__call__(resource['properties'].get(key))
