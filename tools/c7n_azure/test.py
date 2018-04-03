from c7n_azure.session import Session

import pprint


s = Session()
client = s.client('azure.mgmt.compute.ComputeManagementClient')
machines = list(client.virtual_machines.list_all())
# pprint.pprint(machines[0].as_dict())

client = s.client('azure.mgmt.network.NetworkManagementClient')
networks = list(client.virtual_networks.list_all())
pprint.pprint(networks[0].as_dict())
