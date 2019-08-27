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
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('postgresqldatabase')
class PostgresqlDatabase(ChildArmResourceManager):
    """PostgreSQL Database Resource

    The ``azure.postgresqldatabase`` resource is a child resource of the PostgreSQL Server resource,
    and the PostgreSQL Server parent id is available as the ``c7n:parent-id`` property.

    :example:

    Finds all PostgreSQL Databases in the subscription.

    .. code-block:: yaml

        policies:
            - name: find-all-postgresql-databases
              resource: azure.postgresqldatabase
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.postgresql'
        client = 'PostgreSQLManagementClient'
        enum_spec = ('databases', 'list_by_server', None)
        parent_manager_name = 'postgresqlserver'
        resource_type = 'Microsoft.DBforPostgreSQL/servers/databases'

        enable_tag_operations = False  # GH Issue #4543 

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'server_name': parent_resource['name']}
