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
