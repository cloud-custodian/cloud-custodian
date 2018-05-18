# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

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
