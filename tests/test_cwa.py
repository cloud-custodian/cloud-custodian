# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class AlarmTest(BaseTest):

    def test_delete(self):
        alarm_name = "c7n-test-alarm-delete"
        factory = self.replay_flight_data("test_alarm_delete")
        client = factory().client("cloudwatch")
        client.put_metric_alarm(
            AlarmName=alarm_name,
            MetricName="CPUUtilization",
            Namespace="AWS/EC2",
            Statistic="Average",
            Period=3600,
            EvaluationPeriods=5,
            Threshold=10,
            ComparisonOperator="GreaterThanThreshold",
        )

        p = self.load_policy(
            {
                "name": "delete-alarm",
                "resource": "alarm",
                "filters": [{"AlarmName": alarm_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            client.describe_alarms(AlarmNames=[alarm_name])["MetricAlarms"], []
        )

    def test_filter_tags(self):
        factory = self.replay_flight_data("test_alarm_tags_filter")
        p = self.load_policy(
            {
                "name": "filter-alarm-tags",
                "resource": "alarm",
                "filters": [
                    {
                        'type': 'value',
                        'key': 'tag:some-tag',
                        'value': 'some-value',
                        'op': 'eq'
                    }
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('c7n:MatchedFilters'), ['tag:some-tag'])

    def test_add_alarm_tags(self):
        factory = self.replay_flight_data("test_alarm_add_tags")
        p = self.load_policy(
            {
                "name": "add-alarm-tags",
                "resource": "alarm",
                "actions": [{
                    "type": "tag",
                    "key": "OwnerName",
                    "value": "SomeName"
                }],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue({'Key': 'OwnerName', 'Value': 'SomeName'} in resources[0].get('Tags'))

    def test_is_not_composite_child_filter(self):
        factory = self.replay_flight_data("test_is_not_composite_child_filter")
        p = self.load_policy(
            {
                "name": "is-composite-child",
                "resource": "aws.alarm",
                "filters": [
                    {
                        'type': 'is-composite-child',
                        'state': False,
                    }
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 0)

        for alarm in resources:
            self.assertNotIn(alarm['AlarmName'], "c7n-test-alarm-tags-filter")

    def test_is_composite_child_filter(self):
        factory = self.replay_flight_data("test_is_composite_child_filter")
        p = self.load_policy(
            {
                "name": "is-composite-child",
                "resource": "aws.alarm",
                "filters": [
                    {
                        'type': 'is-composite-child',
                        'state': True,
                    }
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        for alarm in resources:
            self.assertIn(alarm['AlarmName'], "c7n-test-alarm-tags-filter")


class CompositeAlarmTest(BaseTest):

    def test_add_composite_alarm_tags(self):
        factory = self.replay_flight_data("test_add_composite_alarm_tags")
        client = factory().client('cloudwatch')
        alarm_arn = "arn:aws:cloudwatch:us-east-1:644160558196:alarm:c7n-composite-alarm"
        p = self.load_policy(
            {
                "name": "add-composite-alarm-tags",
                "resource": "composite-alarm",
                "filters": [{"AlarmArn": alarm_arn}],
                "actions": [{
                    "type": "tag",
                    "key": "OwnerName",
                    "value": "pratyush"
                }],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertFalse({"Key": "OwnerName", "Value": "pratyush"} in resources[0].get('Tags'))
        tags = client.list_tags_for_resource(ResourceARN=alarm_arn).get('Tags')
        self.assertTrue({"Key": "OwnerName", "Value": "pratyush"} in tags)

    def test_delete_composite_alarms(self):
        factory = self.replay_flight_data("test_delete_composite_alarms")
        client = factory().client('cloudwatch')
        p = self.load_policy(
            {
                "name": "delete-composite-alarms",
                "resource": "composite-alarm",
                "filters": [{"AlarmName": "c7n-composite-alarm"}],
                "actions": ["delete"]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        com_alarm = client.describe_alarms(AlarmNames=["c7n-composite-alarm"]).get(
            'CompositeAlarms')
        self.assertEqual(com_alarm, [])
