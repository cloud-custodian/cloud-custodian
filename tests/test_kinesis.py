# Copyright 2016-2017 Capital One Services, LLC
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

from .common import BaseTest, TestConfig as Config


class Kinesis(BaseTest):

    def test_stream_query(self):
        factory = self.replay_flight_data("test_kinesis_stream_query")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [
                    {"type": "value", "value_type": "size", "value": 3, "key": "Shards"}
                ],
            },
            config=Config.empty(),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"], [{"Key": "Origin", "Value": "home"}])
        self.assertEqual(resources[0]["StreamStatus"], "ACTIVE")

    def test_stream_delete(self):
        factory = self.replay_flight_data("test_kinesis_stream_delete")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [{"StreamName": "sock-drawer"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        stream = factory().client("kinesis").describe_stream(StreamName="sock-drawer")[
            "StreamDescription"
        ]
        self.assertEqual(stream["StreamStatus"], "DELETING")

    def test_stream_encrypt(self):
        factory = self.replay_flight_data("test_kinesis_encrypt")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [{"StreamName": "sock-drawer"}],
                "actions": [{"type": "encrypt", "key": "aws/kinesis"}],
            },
            session_factory=factory,
        )
        p.run()
        stream = factory().client("kinesis").describe_stream(StreamName="sock-drawer")[
            "StreamDescription"
        ]
        self.assertEqual(stream["EncryptionType"], "KMS")

    def test_hose_query(self):
        factory = self.replay_flight_data("test_kinesis_hose_query")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"DeliveryStreamName": "sock-index-hose"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DeliveryStreamStatus"], "ACTIVE")

    def test_hose_delete(self):
        factory = self.replay_flight_data("test_kinesis_hose_delete")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"DeliveryStreamName": "sock-index-hose"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            factory().client("firehose").describe_delivery_stream(
                DeliveryStreamName="sock-index-hose"
            )[
                "DeliveryStreamDescription"
            ][
                "DeliveryStreamStatus"
            ],
            "DELETING",
        )

    def test_app_query(self):
        factory = self.replay_flight_data("test_kinesis_analytics_query")
        p = self.load_policy(
            {
                "name": "kapp",
                "resource": "kinesis-analytics",
                "filters": [{"ApplicationStatus": "RUNNING"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ApplicationName"], "sock-app")

    def test_app_delete(self):
        factory = self.replay_flight_data("test_kinesis_analytics_delete")
        p = self.load_policy(
            {
                "name": "kapp",
                "resource": "kinesis-analytics",
                "filters": [{"ApplicationName": "sock-app"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            factory().client("kinesisanalytics").describe_application(
                ApplicationName="sock-app"
            )[
                "ApplicationDetail"
            ][
                "ApplicationStatus"
            ],
            "DELETING",
        )
