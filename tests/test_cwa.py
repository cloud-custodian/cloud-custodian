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
