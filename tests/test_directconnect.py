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


@terraform("directconnect_tagging")
def test_directconnect_tagging(test, directconnect_tagging):
    """DirectConnect APIs return tags in a different format than other services,
    this test ensures that the normalize_tags method in the DirectConnectResource
    class correctly converts the tags to the standard format.
    """
    # Tag
    factory = test.replay_flight_data("test_directconnect_tagging")
    p = test.load_policy(
        {
            "name": "test-directconnect-tagging",
            "resource": "directconnect-gateway",
            "filters": [
                {"directConnectGatewayName": "c7n-test-directconnect-tagging"}
            ],
            "actions": [
                {"type": "tag", "key": "added", "value": "added"}
            ],
        },
        session_factory=factory,
    )

    resources = p.run()

    # Matched the gateway, has an existing tag
    test.assertEqual(len(resources), 1)
    assert resources[0]['tags'] == [{'key': 'existing', 'value': 'existing'}]

    # Confirm that the new tag was added by the action
    client = factory().client("directconnect")
    resource_tags = client.describe_tags(
        resourceArns=[p.resource_manager.generate_arn(resources[0]["directConnectGatewayId"])]
    )["resourceTags"]
    assert len(resource_tags) == 1
    assert resource_tags[0]['tags'] == [
        {'key': 'existing', 'value': 'existing'}, {'key': 'added', 'value': 'added'}
    ]

    # Untag
    p = test.load_policy(
        {
            "name": "test-directconnect-untagging",
            "resource": "directconnect-gateway",
            "filters": [
                {"directConnectGatewayName": "c7n-test-directconnect-tagging"}
            ],
            "actions": [
                {"type": "remove-tag", "tags": ["added"]}
            ],
        },
        session_factory=factory,
        config={'account_id': '495599763451'},
    )

    resources = p.run()

    client = factory().client("directconnect")
    resource_tags = client.describe_tags(
        resourceArns=[p.resource_manager.generate_arn(resources[0]["directConnectGatewayId"])]
    )["resourceTags"]
    assert len(resource_tags) == 1
    assert resource_tags[0]['tags'] == [{'key': 'existing', 'value': 'existing'}]
