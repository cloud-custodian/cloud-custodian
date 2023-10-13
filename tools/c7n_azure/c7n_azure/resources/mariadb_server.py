from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('mariadb-server')
class MariaDBServer(ArmResourceManager):
    """MariaDB Server

    :example:

    Finds all MariaDB instances without Private Endpoint connection configured

    .. code-block:: yaml

        policies:
            - name: asb_mariadb_private_endpoint
              resource: azure.mariadb-server
              filters:
                - type: value
                  key: properties.privateEndpointConnections
                  value: []

    **Warning: Azure MariaDB will be retired on 19 September 2025. Details: https://azure.microsoft.com/en-us/updates/azure-database-for-mariadb-will-be-retired-on-19-september-2025-migrate-to-azure-database-for-mysql-flexible-server/**
    """  # noqa
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.mariadb'
        client = 'MariaDBManagementClient'
        enum_spec = ('servers', 'list', None)
        resource_type = 'Microsoft.DBforMariaDB/servers'
