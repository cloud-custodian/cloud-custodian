from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('synapse')
class Synapse(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Analytics']
        service = 'azure.mgmt.synapse'
        client = 'SynapseManagementClient'
        enum_spec = ('workspaces', 'list', None)
        resource_type = 'Microsoft.Synapse/workspaces'
