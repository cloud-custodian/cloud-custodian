# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


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
