# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import Filter
from c7n.utils import type_schema


@resources.register('sqlserver')
class SqlServer(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('servers', 'list', None)


@SqlServer.filter_registry.register('sql-database-view')
class SqlDatabaseViewFilter(Filter):

    schema = type_schema('sql-database-view')

    def __call__(self, i, *args, **kwargs):

        if 'databases' not in i:
            client = self.manager.get_client()
            resource_group = i['resourceGroup']
            server_name = i['name']
            dbs = client.databases.list_by_server(resource_group, server_name)
            i['databases'] = [db.serialize() for db in dbs]

        return True
