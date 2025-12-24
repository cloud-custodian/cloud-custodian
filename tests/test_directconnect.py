# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform


@terraform("directconnect_gateway")
def test_directconnect_gateway(test, directconnect_gateway):
    factory = test.replay_flight_data("test_directconnect_gateway")
    p = test.load_policy(
        {
            "name": "test-directconnect-gateway",
            "resource": "directconnect-gateway",
            "filters": [
                {"directConnectGatewayName": "c7n-test-directconnect-gateway"}
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(
        resources[0]["directConnectGatewayId"],
        directconnect_gateway["aws_dx_gateway.test_gateway.id"]
    )


def test_directconnect_vif(test):
    factory = test.replay_flight_data("test_directconnect_vif")
    p = test.load_policy(
        {
            "name": "test-directconnect-vif",
            "resource": "directconnect-virtual-interface",
            "filters": [
                {"virtualInterfaceName": "Test-VIF"}
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
