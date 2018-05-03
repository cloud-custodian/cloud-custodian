from c7n_azure.session import Session
from azure.mgmt.resource import ResourceManagementClient
import pprint
import os


s = Session()
client = s.client('azure.mgmt.resource.ResourceManagementClient')
resource_group_params = {'location': 'westus'}
resource_group_params.update(tags={'hello': 'world'})

for item in client.resources.list():
    print(s.resource_api_version(item.id))
