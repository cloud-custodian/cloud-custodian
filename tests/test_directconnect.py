# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest


class DirectConnectVirtualInterfaceTest(BaseTest):

    def test_directconnect_virtual_interface(self):
        session_factory = self.replay_flight_data("test_directconnect_virtual_interface")

        p = self.load_policy(
            {
                "name": "directconnect-vif",
                "resource": "directconnect-vif",
                "filters": [
                    {
                        "type": "value",
                        "key": "ownerAccount",
                        "value": "109876543210",
                        "op": "not-equal",
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ownerAccount'], 'XXXXXXXXXXXX')


class DirectConnectGatewayTest(BaseTest):

    def test_directconnect_gateway(self):
        session_factory = self.replay_flight_data("test_directconnect_gateway")

        p = self.load_policy(
            {
                "name": "directconnect-gateway",
                "resource": "directconnect-gateway",
                "filters": [
                    {
                        "type": "value",
                        "key": "directConnectGatewayId",
                        "value": "dc-gateway-id",
                        "op": "equal",
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['directConnectGatewayName'], 'dc-gateway-name')

    def test_directconnect_gateway_associations(self):
        session_factory = self.replay_flight_data("test_directconnect_gateway_associations")

        p = self.load_policy(
            {
                "name": "directconnect-gateway",
                "resource": "directconnect-gateway",
                "filters": [
                    {
                        "type": "associations",
                        "key": "directConnectGatewayAssociations[].associatedGateway.ownerAccount",
                        "value": ["XXXXXXXXXXX", "YYYYYYYYYYYY", "ZZZZZZZZZZZZ", "XYZXYZXYZXYZ"],
                        "op": "intersect"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['directConnectGatewayName'], 'test-custodian-directconnect-gateway')
