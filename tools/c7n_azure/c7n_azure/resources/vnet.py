from c7n_azure.query import QueryResourceManager
from c7n.provider import azure


@azure.register('vnet')
class Vnet(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        ops = 'virtual_networks'
        
