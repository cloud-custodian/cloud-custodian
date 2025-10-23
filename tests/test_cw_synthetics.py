from .common import BaseTest


class SyntheticsCanaryTest(BaseTest):

    def test_canary_filter_by_tag(self):
        factory = self.replay_flight_data("test_cw_synthetics_tag_filter")
        canary_name = "test_canary_tag"

        p = self.load_policy(
            {
                "name": "filter-canary-by-tag",
                "resource": "cloudwatch-synthetics",
                "filters": [
                    {"type": "value", "key": "tag:MyTagKey", "value": "MyTagValue"}
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], canary_name)
        self.assertEqual(resources[0].get("c7n:MatchedFilters"), ["tag:MyTagKey"])

    def test_delete_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_delete")
        client = factory().client("synthetics")

        canary_name = "test_canary_delete"

        p = self.load_policy(
            {
                "name": "delete-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        canaries = client.describe_canaries()["Canaries"]
        # After deletion, canary should either be gone or in DELETING state
        target_canary = next((c for c in canaries if c["Name"] == canary_name), None)
        if target_canary is not None:
            self.assertEqual(target_canary["Status"]["State"], "DELETING")
        # If target_canary is None, that's also acceptable (fully deleted)

    def test_stop_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_stop")
        client = factory().client("synthetics")

        canary_name = "test_canary_stop"

        p = self.load_policy(
            {
                "name": "stop-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["stop"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        desc = client.get_canary(Name=canary_name)
        self.assertIn(desc["Canary"]["Status"]["State"], ["STOPPED", "STOPPING"])

    def test_start_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_start")
        client = factory().client("synthetics")

        canary_name = "test_canary_start"

        p = self.load_policy(
            {
                "name": "start-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["start"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        desc = client.get_canary(Name=canary_name)
        self.assertIn(desc["Canary"]["Status"]["State"], ["RUNNING", "STARTING"])

    def test_endpoint_url_error_paths(self):
        """Test error handling paths in endpoint URL extraction"""
        from unittest.mock import patch, MagicMock

        factory = self.replay_flight_data("test_cw_synthetics_tag_filter")

        p = self.load_policy(
            {
                "name": "test-endpoint-url-errors",
                "resource": "cloudwatch-synthetics",
            },
            session_factory=factory,
        )

        # Test case 1: No runs available (covers lines 876-877)
        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_synthetics = MagicMock()
            mock_s3 = MagicMock()
            mock_session.return_value.client.side_effect = (
                lambda x: mock_synthetics if x == 'synthetics' else mock_s3
            )

            # Mock empty runs
            mock_synthetics.get_canary_runs.return_value = {"CanaryRuns": []}

            # Create a test resource
            test_resource = {
                "Name": "test-canary",
                "Tags": {"TestKey": "TestValue"}
            }

            # Call augment directly
            result = p.resource_manager.augment([test_resource])

            # Verify DestinationUrl is None when no runs
            self.assertIsNone(result[0]["DestinationUrl"])

        # Test case 2: No artifact location (covers lines 881-882)
        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_synthetics = MagicMock()
            mock_s3 = MagicMock()
            mock_session.return_value.client.side_effect = (
                lambda x: mock_synthetics if x == 'synthetics' else mock_s3
            )

            # Mock runs without artifact location
            mock_synthetics.get_canary_runs.return_value = {
                "CanaryRuns": [{"Status": {"State": "PASSED"}}]  # Missing ArtifactS3Location
            }

            test_resource = {
                "Name": "test-canary",
                "Tags": {"TestKey": "TestValue"}
            }

            result = p.resource_manager.augment([test_resource])

            # Verify DestinationUrl is None when no artifact
            self.assertIsNone(result[0]["DestinationUrl"])
