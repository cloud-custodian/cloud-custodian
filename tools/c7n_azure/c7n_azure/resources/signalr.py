from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('signalr')
class Signalr(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']
        service = 'azure.mgmt.signalr'
        client = 'SignalRManagementClient'
        enum_spec = ('signal_r', 'list_by_subscription', None)
        resource_type = 'Microsoft.SignalRService/signalR'
