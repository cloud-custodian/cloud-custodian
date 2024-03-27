from ..azure_common import BaseTest


class SubnetApplicationGatewayTest(BaseTest):

    def test_subnet_application_gateway_filter(self):
        p = self.load_policy(
            {
                "name": "test-subnet-application-gateway",
                "resource": "azure.vnet",
                "filters": [
                    {
                        "type": "subnet-application-gateway"},
                    {
                        "type": "value",
                        "key": "properties.ddosProtectionPlan.id",
                        "value": r"\/.+\/ddosProtectionPlans\/.+",
                        "op": "regex",
                    },
                    {
                        "type": "value",
                        "key": "properties.enableDdosProtection",
                        "value": True,
                    }
                ],
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_vnet_network_interface_assignment_filter(self):
        p = self.load_policy({
            "name": "test-vnet-network-interface-assignment-filter",
            "resource": "azure.vnet",
            "filters": [{
                "type": "network-interface-assignment",
                "key": "virtual_machine",
                "value": "present"
            }]
        })
        resources = p.run()

        self.assertEqual(2, len(resources))
        self.assertEqual('vnet1-141asbfwroute', resources[0]['name'])
        self.assertEqual('TM-RM-vnet', resources[1]['name'])
