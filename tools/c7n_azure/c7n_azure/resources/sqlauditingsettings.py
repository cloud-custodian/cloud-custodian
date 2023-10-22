# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
# limitations under the License.from c7n_azure.provider import resources

import logging

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager

log = logging.getLogger('custodian.azure.sqlauditingsettings')


@resources.register('sql-auditing-settings', aliases=['sqlauditingsettings'])
class SqlAuditingSettings(ChildArmResourceManager):
    """SQL Server Auditing Settings Resource

    The ``azure.sqlauditingsettings`` resource is a child resource of the SQL Server resource,
    and the SQL Server parent id is available as the ``c7n:parent-id`` property.

    :example:

    Retrieves SQL Server Auditing Settings.

    .. code-block:: yaml

        policies:
            - name: retrieve-azure-sql-auditing-settings
              resource: azure.sql-auditing-settings

    """
    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('server_blob_auditing_policies', 'list_by_server', None)
        parent_manager_name = 'sqlserver'
        resource_type = 'Microsoft.Sql/servers/databases/auditingSettings'
        id = name = 'id'
        default_report_fields = ('"c7n:parent-id"', 'properties.state', 'properties.retentionDays')

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'server_name': parent_resource['name']}
