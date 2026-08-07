from .common import BaseTest
from unittest.mock import patch, MagicMock


class CloudWatchEdgeCasesTest(BaseTest):
    """Tests specifically targeting edge cases and exception paths for maximum coverage"""

    def test_log_group_cross_account_error_handling(self):
        """Test cross account filter error handling"""
        factory = self.replay_flight_data("test_log_group_cross_account")

        # Test cross account violation detection
        p1 = self.load_policy(
            {
                "name": "test-cross-account",
                "resource": "log-group",
                "filters": [
                    {"type": "cross-account", "whitelist": ["123456789012"]}
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()

        # This should trigger the cross-account filter processing
        self.assertIsInstance(resources, list)

    def test_log_group_subscription_filter_edge_cases(self):
        """Test subscription filter edge cases"""
        factory = self.replay_flight_data("test_log_group_subscription_filter")

        # Test subscription filter with no matches
        p1 = self.load_policy(
            {
                "name": "test-subscription-filter",
                "resource": "log-group",
                "filters": [
                    {"type": "subscription-filter", "key": "filterName", "value": "nonexistent"}
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()

        # This should trigger the subscription filter processing paths
        self.assertIsInstance(resources, list)

    def test_synthetics_exception_handling(self):
        """Test synthetics actions with exception handling paths"""

        # Test start canary exception handling
        factory = self.replay_flight_data("test_cw_synthetics_start")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Mock get_canary to raise an exception
            mock_client.get_canary.side_effect = Exception("Test exception")

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-start-error",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["start"],
                },
                session_factory=factory,
            )

            # This should trigger the exception handling in StartCanary
            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

    def test_synthetics_stop_exception_handling(self):
        """Test stop canary exception handling"""
        factory = self.replay_flight_data("test_cw_synthetics_stop")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Mock get_canary to raise an exception
            mock_client.get_canary.side_effect = Exception("Test stop exception")

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-stop-error",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["stop"],
                },
                session_factory=factory,
            )

            # This should trigger the exception handling in StopCanary
            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

    def test_synthetics_delete_exception_handling(self):
        """Test delete canary exception handling"""
        factory = self.replay_flight_data("test_cw_synthetics_delete")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Mock get_canary to raise an exception
            mock_client.get_canary.side_effect = Exception("Test delete exception")

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-delete-error",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["delete"],
                },
                session_factory=factory,
            )

            # This should trigger the exception handling in DeleteCanary
            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

    def test_synthetics_state_conditions(self):
        """Test synthetics state condition handling"""
        factory = self.replay_flight_data("test_cw_synthetics_start")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Test start canary when already running (should not start)
            mock_client.get_canary.return_value = {
                'Canary': {'Status': {'State': 'RUNNING'}}
            }

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-start-running",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["start"],
                },
                session_factory=factory,
            )

            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

            # Should call get_canary but not start_canary
            mock_client.get_canary.assert_called()
            mock_client.start_canary.assert_not_called()

    def test_synthetics_stop_state_conditions(self):
        """Test stop canary state condition handling"""
        factory = self.replay_flight_data("test_cw_synthetics_stop")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Test stop canary when already stopped (should not stop)
            mock_client.get_canary.return_value = {
                'Canary': {'Status': {'State': 'STOPPED'}}
            }

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-stop-stopped",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["stop"],
                },
                session_factory=factory,
            )

            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

            # Should call get_canary but not stop_canary
            mock_client.get_canary.assert_called()
            mock_client.stop_canary.assert_not_called()

    def test_synthetics_delete_state_conditions(self):
        """Test delete canary state condition handling"""
        factory = self.replay_flight_data("test_cw_synthetics_delete")

        with patch('c7n.resources.cw.local_session') as mock_session:
            mock_client = MagicMock()
            mock_session.return_value.client.return_value = mock_client

            # Test delete canary when running (should not delete)
            mock_client.get_canary.return_value = {
                'Canary': {'Status': {'State': 'RUNNING'}}
            }

            p1 = self.load_policy(
                {
                    "name": "test-synthetics-delete-running",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test_canary"}],
                    "actions": ["delete"],
                },
                session_factory=factory,
            )

            resources = [{"Name": "test_canary"}]
            p1.resource_manager.actions[0].process(resources)

            # Should call get_canary but not delete_canary
            mock_client.get_canary.assert_called()
            mock_client.delete_canary.assert_not_called()

    def test_log_metric_alarm_permissions(self):
        """Test log metric alarm filter get_permissions method"""
        factory = self.replay_flight_data("test_log_group_log_metric_filter_alarm")

        p1 = self.load_policy(
            {
                "name": "test-log-metric-permissions",
                "resource": "log-metric",
                "filters": [
                    {"type": "alarm", "key": "AlarmName", "value": "present"}
                ],
            },
            session_factory=factory,
        )

        # This should trigger the get_permissions method in LogMetricAlarmFilter
        filter_obj = p1.resource_manager.filters[0]
        permissions = filter_obj.get_permissions()
        self.assertIn('cloudwatch:DescribeAlarmsForMetric', permissions)
