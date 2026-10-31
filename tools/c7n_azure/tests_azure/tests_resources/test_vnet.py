from ..azure_common import BaseTest


class VnetNetworkInterfaceFilter(BaseTest):

    def test_vm_network_interface(self):
        p = self.load_policy({
            'name': 'test-vnet-network-interface',
            'resource': 'azure.vnet',
            'filters': [{
                'type': 'network-interface',
                'attrs': [{
                    'type': 'value',
                    'key': 'properties.virtualMachine',
                    'value': 'present'
                }]
            }]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'vnet1-141asbfwroute')
        self.assertEqual(len(resources[0]['c7n:NetworkInterfaces']), 1)
