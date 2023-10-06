from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('mariadb-server')
class MariaDBServer(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.rdbms.mariadb'
        client = 'MariaDBManagementClient'
        enum_spec = ('servers', 'list', None)
        resource_type = 'Microsoft.DBforMariaDB/servers'
