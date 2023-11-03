from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('kusto')
class Kusto(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Analytics']
        service = 'azure.mgmt.kusto'
        client = 'KustoManagementClient'
        enum_spec = ('clusters', 'list', None)
        resource_type = 'Microsoft.Kusto/clusters'
        diagnostic_settings_enabled = False
