# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock
from .common import BaseTest


class TestNetworkManager(BaseTest):

    def test_list_core_networks(self):
        session_factory = self.replay_flight_data("test_networkmanager_list_core_networks")
        p = self.load_policy(
            {
                "name": "list-core-networks",
                "resource": "networkmanager-core",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")
            self.assertTrue(r["CoreNetworkArn"])
            self.assertTrue("Edges" in r)
            self.assertTrue("Segments" in r)

    def test_list_core_networks_filter_out_shared_ram_networks(self):
        # Test Core Networks shared from RAM are filtered out
        # The test data has 2 Core Networks, one of which is shared from RAM
        # Shared networks are detected by the 'OwnerAccountId' field
        session_factory = self.replay_flight_data(
            "test_networkmanager_core_networks_exclude_ram")
        p = self.load_policy(
            {
                "name": "list-core-networks-verify-exclude-ram",
                "resource": "networkmanager-core",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertNotEqual(r['OwnerAccountId'], '123456789012')

    def test_describe_global_networks(self):
        session_factory = self.replay_flight_data("test_networkmanager_describe_global_networks")
        p = self.load_policy(
            {
                "name": "describe_global_networks",
                "resource": "networkmanager-global",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")

    def test_describe_specific_global_network(self):
        session_factory = self.replay_flight_data(
            "test_networkmanager_describe_specific_global_network")
        p = self.load_policy(
            {
                "name": "describe_global_networks",
                "resource": "networkmanager-global",
                "filters": [
                    {"GlobalNetworkId": "global-network-0f952aba212c3fb47"}
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GlobalNetworkId"], "global-network-0f952aba212c3fb47")

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")

    def test_tag_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_tag_core_network")
        p = self.load_policy(
            {
                "name": "tag-core-network",
                "resource": "networkmanager-core",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
            "actions": [{"type": "tag", "key": "Category", "value": "TestValue"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["CoreNetworkArn"])["TagList"]
        self.assertEqual(tags[0]["Value"], "TestValue")

    def test_remove_tag_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_remove_tag_core_network")
        p = self.load_policy(
            {
                "name": "untag-core-network",
                "resource": "networkmanager-core",
                "filters": [{"tag:Name": "test-cloudwan"}],
                "actions": [{"type": "remove-tag", "tags": ["Category"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["CoreNetworkArn"])["TagList"]
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], "Name")

    def test_delete_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_core_network")
        p = self.load_policy(
            {
                "name": "delete-core-network",
                "resource": "networkmanager-core",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        core_network = client.get_core_network(
            CoreNetworkId=resources[0]["CoreNetworkId"])['CoreNetwork']
        self.assertEqual(core_network['State'], "DELETING")

    def test_delete_global_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_global_network")
        p = self.load_policy(
            {
                "name": "delete-global-network",
                "resource": "networkmanager-global",
                "filters": [
                    {"tag:Name": "test-cloudwan-2"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        global_network = client.describe_global_networks(
            GlobalNetworkIds=[resources[0]["GlobalNetworkId"]])['GlobalNetworks']
        self.assertTrue(len(global_network) == 0)

    def test_mark_for_op_core_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_mark_for_op_core_network")
        p = self.load_policy(
            {
                "name": "mark-for-op-core-network",
                "resource": "networkmanager-core",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
                "actions": [{"type": "mark-for-op", "op": "delete", "days": 1}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        core_network = client.get_core_network(
            CoreNetworkId=resources[0]["CoreNetworkId"])['CoreNetwork']
        self.assertTrue([t for t in core_network['Tags'] if t['Key'] == 'maid_status'])

    def test_mark_for_op_global_network(self):
        session_factory = self.replay_flight_data("test_networkmanager_mark_for_op_global_network")
        p = self.load_policy(
            {
                "name": "mark-for-op-global-network",
                "resource": "networkmanager-global",
                "filters": [
                    {"tag:Name": "test-cloudwan"}
                ],
                "actions": [{"type": "mark-for-op", "op": "delete", "days": 1}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        global_network = client.describe_global_networks(
            GlobalNetworkIds=[resources[0]["GlobalNetworkId"]])['GlobalNetworks']
        self.assertTrue([t for t in global_network[0]['Tags'] if t['Key'] == 'maid_status'])

    def test_core_network_delete_error(self):
        invalid_network_id = 'core-network-7a6b617270696e736b69'
        factory = self.record_flight_data("test_core_network_delete_error")
        client = factory().client("networkmanager")
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client(
            'networkmanager').exceptions.ResourceNotFoundException = (
                client.exceptions.ResourceNotFoundException)
        mock_factory().client('networkmanager').delete_core_network.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_core_network'))
        p = self.load_policy({
            'name': 'delete-core-network-error',
            'resource': 'networkmanager-core',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'CoreNetworkId': invalid_network_id}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        mock_factory().client('networkmanager').delete_core_network.assert_called_once()

    def test_global_network_delete_error(self):
        invalid_network_id = 'global-network-7a6b617270696e736b69'
        factory = self.replay_flight_data("test_networkmanager_delete_global_network")
        client = factory().client("networkmanager")
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client(
            'networkmanager').exceptions.ResourceNotFoundException = (
                client.exceptions.ResourceNotFoundException)
        mock_factory().client('networkmanager').delete_global_network.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_global_network'))
        p = self.load_policy({
            'name': 'delete-global-network-error',
            'resource': 'networkmanager-global',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'GlobalNetworkId': invalid_network_id}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        mock_factory().client('networkmanager').delete_global_network.assert_called_once()


class TestNetworkManagerSites(BaseTest):
    def test_list_sites(self):
        session_factory = self.replay_flight_data("test_networkmanager_list_sites")
        p = self.load_policy(
            {
                "name": "list-sites",
                "resource": "networkmanager-site",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")
            self.assertTrue(r["SiteId"])

    def test_tag_site(self):
        session_factory = self.replay_flight_data("test_networkmanager_tag_site")
        p = self.load_policy(
            {
                "name": "tag-site",
                "resource": "networkmanager-site",
            "actions": [{"type": "tag", "key": "c7n", "value": "test"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["SiteArn"])["TagList"]
        self.assertEqual(tags[0]["Value"], "test")

    def test_untag_site(self):
        session_factory = self.replay_flight_data("test_networkmanager_untag_site")
        p = self.load_policy(
            {
                "name": "untag-site",
                "resource": "networkmanager-site",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["SiteArn"])["TagList"]
        self.assertEqual(len(tags), 1)
        self.assertTrue(tags[0]['Key'], "Name")

    def test_delete_site(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_site")
        p = self.load_policy(
            {
                "name": "delete-site",
                "resource": "networkmanager-site",
                "filters": [
                    {"tag:deleteme": "delete"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_site_delete_error(self):
        invalid_site_id = 'site-7a6b617270696e736b69'
        invalid_network_id = 'global-network-7a6b617270696e736b69'
        mock_factory = MagicMock()
        mock_factory.region = 'us-west-2'
        client = mock_factory().client('networkmanager')

        client.delete_site.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_site'))
        p = self.load_policy({
            'name': 'delete-site-error',
            'resource': 'networkmanager-site',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'GlobalNetworkId': invalid_network_id,
                    'SiteId': invalid_site_id}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        client.delete_site.assert_called_once()


class TestNetworkManagerDevices(BaseTest):
    def test_list_devices(self):
        session_factory = self.replay_flight_data("test_networkmanager_list_devices")
        p = self.load_policy(
            {
                "name": "list-devices",
                "resource": "networkmanager-device",
                "filters": [{
                    "State": "AVAILABLE"
                }]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")
            self.assertTrue(r["DeviceId"])

    def test_tag_device(self):
        session_factory = self.replay_flight_data("test_networkmanager_tag_device")
        p = self.load_policy(
            {
                "name": "tag-device",
                "resource": "networkmanager-device",
                "filters": [{"tag:Name": "test-device"}],
                "actions": [{"type": "tag", "key": "c7n", "value": "test"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["DeviceArn"])["TagList"]
        self.assertEqual(tags[0]["Value"], "test")

    def test_untag_device(self):
        session_factory = self.replay_flight_data("test_networkmanager_untag_device")
        p = self.load_policy(
            {
                "name": "untag-device",
                "resource": "networkmanager-device",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["DeviceArn"])["TagList"]
        self.assertEqual(len(tags), 1)
        self.assertTrue(tags[0]['Key'], "Name")

    def test_delete_device(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_device")
        p = self.load_policy(
            {
                "name": "delete-device",
                "resource": "networkmanager-device",
                "filters": [
                    {"tag:deleteme": "delete"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_device_delete_error(self):
        invalid_device_id = 'device-7a6b617270696e736b69'
        invalid_network_id = 'global-network-7a6b617270696e736b69'
        mock_factory = MagicMock()
        mock_factory.region = 'us-west-2'
        client = mock_factory().client('networkmanager')
        client.delete_device.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_device'))
        p = self.load_policy({
            'name': 'delete-device-error',
            'resource': 'networkmanager-device',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'GlobalNetworkId': invalid_network_id,
                    'DeviceId': invalid_device_id}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        client.delete_device.assert_called_once()


class TestNetworkManagerLinks(BaseTest):
    def test_list_links(self):
        session_factory = self.replay_flight_data("test_networkmanager_list_links")
        p = self.load_policy(
            {
                "name": "list-links",
                "resource": "networkmanager-link",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        for r in resources:
            self.assertEqual(r["State"], "AVAILABLE")
            self.assertTrue(r["LinkId"])

    def test_tag_link(self):
        session_factory = self.replay_flight_data("test_networkmanager_tag_link")
        p = self.load_policy(
            {
                "name": "tag-link",
                "resource": "networkmanager-link",
                "filters": [{"tag:Name": "test-link"}],
                "actions": [{"type": "tag", "key": "c7n", "value": "test"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["LinkArn"])["TagList"]
        self.assertEqual(tags[0]["Value"], "test")

    def test_untag_link(self):
        session_factory = self.replay_flight_data("test_networkmanager_untag_link")
        p = self.load_policy(
            {
                "name": "untag-link",
                "resource": "networkmanager-link",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("networkmanager")
        tags = client.list_tags_for_resource(ResourceArn=resources[0]["LinkArn"])["TagList"]
        self.assertEqual(len(tags), 1)
        self.assertTrue(tags[0]['Key'], "Name")

    def test_delete_link(self):
        session_factory = self.replay_flight_data("test_networkmanager_delete_link")
        p = self.load_policy(
            {
                "name": "delete-link",
                "resource": "networkmanager-link",
                "filters": [
                    {"tag:deleteme": "delete"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_link_delete_error(self):
        invalid_link_id = 'link-7a6b617270696e736b69'
        invalid_network_id = 'global-network-7a6b617270696e736b69'
        mock_factory = MagicMock()
        mock_factory.region = 'us-west-2'
        client = mock_factory().client('networkmanager')
        client.delete_link.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_link'))
        p = self.load_policy({
            'name': 'delete-link-error',
            'resource': 'networkmanager-link',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'GlobalNetworkId': invalid_network_id,
                    'LinkId': invalid_link_id}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        client.delete_link.assert_called_once()
