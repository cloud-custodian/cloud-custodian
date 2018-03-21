from c7n_azure.query import QueryResourceManager
from c7n.provider import azure


@azure.register('vm')
class VirtualMachine(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        ops = 'virtual_machines'        
        
