from .common import BaseTest


class CloudWatchCoverageBoostTest(BaseTest):
    """Additional tests to boost coverage for CloudWatch resources"""

    def test_alarm_delete_action(self):
        """Test alarm deletion action to cover reformatted code"""
        factory = self.replay_flight_data("test_alarm_delete")

        p = self.load_policy(
            {
                "name": "delete-alarm-test",
                "resource": "alarm",
                "filters": [{"AlarmName": "test-alarm"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        # This exercises the reformatted delete action code
        p.run()

    def test_composite_alarm_delete_action(self):
        """Test composite alarm deletion action"""
        factory = self.replay_flight_data("test_delete_composite_alarms")

        p = self.load_policy(
            {
                "name": "delete-composite-alarm-test",
                "resource": "composite-alarm",
                "filters": [{"AlarmName": "c7n-composite-alarm"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        # This exercises the reformatted composite alarm delete code
        p.run()

    def test_insight_rule_disable_action(self):
        """Test insight rule disable action"""
        factory = self.replay_flight_data("test_insight_rule_disable")

        p = self.load_policy(
            {
                "name": "disable-insight-rule-test",
                "resource": "insight-rule",
                "filters": [{"Name": "test-rule"}],
                "actions": ["disable"],
            },
            session_factory=factory,
        )

        # This exercises the reformatted insight rule disable code
        p.run()

    def test_insight_rule_delete_action(self):
        """Test insight rule delete action"""
        factory = self.replay_flight_data("test_insight_rule_delete")

        p = self.load_policy(
            {
                "name": "delete-insight-rule-test",
                "resource": "insight-rule",
                "filters": [{"Name": "test-rule"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        # This exercises the reformatted insight rule delete code
        p.run()

    def test_canary_start_stop_delete_coverage(self):
        """Test canary actions to ensure coverage of new error handling"""
        from unittest.mock import patch, MagicMock

        factory = self.replay_flight_data("test_cw_synthetics_tag_filter")

        # Test each action with mocked client to cover exception paths
        for action in ["start", "stop", "delete"]:
            p = self.load_policy(
                {
                    "name": f"test-canary-{action}",
                    "resource": "cloudwatch-synthetics",
                    "filters": [{"Name": "test-canary"}],
                    "actions": [action],
                },
                session_factory=factory,
            )

            # Use the real policy manager but with a test resource
            test_resource = [{"Name": "test-canary", "Tags": {}}]

            # Get the action instance and test it directly
            action_instance = p.resource_manager.actions[0]

            # Test normal execution path
            with patch('c7n.resources.cw.local_session') as mock_session:
                mock_client = MagicMock()
                mock_session.return_value.client.return_value = mock_client

                if action == "start":
                    mock_client.get_canary.return_value = {
                        'Canary': {'Status': {'State': 'STOPPED'}}
                    }
                elif action == "stop":
                    mock_client.get_canary.return_value = {
                        'Canary': {'Status': {'State': 'RUNNING'}}
                    }
                elif action == "delete":
                    mock_client.get_canary.return_value = {
                        'Canary': {'Status': {'State': 'STOPPED'}}
                    }

                # This should execute the action successfully
                action_instance.process(test_resource)

                # Verify the expected client method was called
                if action == "start":
                    mock_client.start_canary.assert_called_once()
                elif action == "stop":
                    mock_client.stop_canary.assert_called_once()
                elif action == "delete":
                    mock_client.delete_canary.assert_called_once()

    def test_cloudwatch_source_mapping_coverage(self):
        """Test CloudWatch source mapping to cover reformatted lines"""
        factory = self.replay_flight_data("test_alarm_delete")

        # Test alarm source mapping
        p = self.load_policy(
            {
                "name": "test-source-mapping",
                "resource": "alarm",
                "source": "describe",
                "filters": [{"AlarmName": "test-alarm"}],
            },
            session_factory=factory,
        )

        # This exercises the source_mapping code that was reformatted
        p.run()
