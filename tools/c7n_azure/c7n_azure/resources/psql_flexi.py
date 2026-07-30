# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.actions.base import AzureBaseAction


@resources.register('postgresql-flexible-server')
class PostgresqlServer(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.postgresql_flexibleservers'
        client = 'PostgreSQLManagementClient'
        enum_spec = ('servers', 'list', None)
        resource_type = 'Microsoft.DBforPostgreSQL/flexibleServers/configurations'


@PostgresqlServer.action_registry.register('stop')
class StopPostgresqlServer(AzureBaseAction):

    schema = type_schema('stop')

    def _prepare_processing(self):
        fs_client = 'azure.mgmt.rdbms.postgresql_flexibleservers.PostgreSQLManagementClient'
        self.client = self.manager.get_client(fs_client)

    def _process_resource(self, resource):
        self.client.servers.begin_stop(resource['resourceGroup'], resource['name'])

@PostgresqlServer.action_registry.register('start')
class StartPostgresqlServer(AzureBaseAction):

    schema = type_schema('start')

    def _prepare_processing(self):
        fs_client = 'azure.mgmt.rdbms.postgresql_flexibleservers.PostgreSQLManagementClient'
        self.client = self.manager.get_client(fs_client)

    def _process_resource(self, resource):
        self.client.servers.begin_start(resource['resourceGroup'], resource['name'])
