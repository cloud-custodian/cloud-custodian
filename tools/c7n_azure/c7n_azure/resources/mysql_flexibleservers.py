# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.filters.core import ValueFilter, type_schema


@resources.register('mysql-flexibleservers')
class MySQLFlexibleServer(ArmResourceManager):
    """Azure MySQL Flexible Server Resource

    :example:

    This policy will find all mysql flexible servers with minimum TLS Version of TLSV1.2

    .. code-block:: yaml

        policies:
          - name: mysql-flexible-server-tls-version
            resource: azure.mysql-flexibleservers
            filters:
              - type: value
                key: tls_version
                op: ne
                value: 'TLSv1.2'

    """

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
        resource_type = 'Microsoft.DBForMySQL/servers/flexibleservers/configurations'

@MySQLFlexibleServer.filter_registry.register('server-parameter')
class ServerParametersFilter(ValueFilter):
     """Filter by configuration parameter for this postresql server

     Configurations are made available to the filter as a map with each
     key holding the name of the configuration and each value holding
     the properties of the Configuration as defined here:
     https://learn.microsoft.com/en-us/python/api/azure-mgmt-rdbms/azure.mgmt.rdbms.mysql_flexibleservers.models.configuration?view=azure-python

     :example:

     Example JSON document showing the data format provided to the filter

     .. code-block:: json

       {
         "allowedValues": "TLSv1,TLSv1.1,TLSv1.2",
         "dataType": "Set",
         "defaultValue": "TLSv1.2",
         "description": "Which protocols the server permits for encrypted connections.",
         "isConfigPendingRestart": "False",
         "isDynamicConfig": "False",
         "name": "tls_version",
         "source": "system-default",
         "value": "TLSv1.2"
       }
        
     :example:

     Find Mysql flexible server with TLSv1.2 

     .. code-block:: yaml

         policies:
           - name: sql-database-no-log-connections
             resource: azure.mysql-flexibleservers
             filters:
               - type: server-parameter
                 name: tls_version
                 key: value
                 op: ne
                 value: 'TLSv1.2'

     """

     schema = type_schema(
         'server-parameter',
         required=['type', 'name'],
         rinherit=ValueFilter.schema,
         name=dict(type='string')
     )

     def __call__(self, resource):
         key = f'c7n:server-params:{self.data["name"]}'
         if key not in resource['properties']:
             client = self.manager.get_client()
             query = client.configurations.get(
                 resource['resourceGroup'],
                 resource['name'],
                 self.data["name"]
             )

             resource['properties'][key] = query.serialize(True).get('properties')

         return super().__call__(resource['properties'][key])
