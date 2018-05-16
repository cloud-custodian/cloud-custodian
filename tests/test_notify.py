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

from .common import BaseTest, functional

import base64
import json
import time
import tempfile
import zlib


class NotifyTest(BaseTest):

    @functional
    def test_notify_address_from(self):
        session_factory = self.replay_flight_data("test_notify_address_from")
        client = session_factory().client("sqs")
        queue_url = client.create_queue(QueueName="c7n-notify-test")["QueueUrl"]

        def cleanup():
            client.delete_queue(QueueUrl=queue_url)
            if self.recording:
                time.sleep(60)

        self.addCleanup(cleanup)
        temp_file = tempfile.NamedTemporaryFile(mode="w")
        json.dump({"emails": ["me@example.com"]}, temp_file)
        temp_file.flush()
        self.addCleanup(temp_file.close)

        policy = self.load_policy(
            {
                "name": "notify-address",
                "resource": "sqs",
                "filters": [{"QueueUrl": queue_url}],
                "actions": [
                    {
                        "type": "notify",
                        "to": ["to@example.com"],
                        "to_from": {
                            "url": "file://%s" % temp_file.name,
                            "format": "json",
                            "expr": "emails",
                        },
                        "cc_from": {
                            "url": "file://%s" % temp_file.name,
                            "format": "json",
                            "expr": "emails",
                        },
                        "transport": {"type": "sqs", "queue": queue_url},
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(policy.data.get("actions")[0].get("to"), ["to@example.com"])
        self.assertEqual(len(resources), 1)
        messages = client.receive_message(
            QueueUrl=queue_url, AttributeNames=["All"]
        ).get(
            "Messages", []
        )
        self.assertEqual(len(messages), 1)

        body = json.loads(zlib.decompress(base64.b64decode(messages[0]["Body"])))
        self.assertEqual(
            set(body.keys()),
            set(
                (
                    "account_id",
                    "action",
                    "event",
                    "policy",
                    "region",
                    "account",
                    "resources",
                )
            ),
        )

    def test_sns_notify(self):
        session_factory = self.replay_flight_data("test_sns_notify_action")
        client = session_factory().client("sns")
        topic = client.create_topic(Name="c7n-notify-test")["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic)

        policy = self.load_policy(
            {
                "name": "notify-sns",
                "resource": "sns",
                "filters": [{"TopicArn": topic}],
                "actions": [
                    {
                        "type": "notify",
                        "to": ["noone@example.com"],
                        "transport": {"type": "sns", "topic": topic},
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_notify(self):
        session_factory = self.replay_flight_data("test_notify_action", zdata=True)
        policy = self.load_policy(
            {
                "name": "instance-check",
                "resource": "ec2",
                "filters": [{"tag:Testing": "Testing123"}],
                "actions": [
                    {
                        "type": "notify",
                        "to": ["someon@example.com"],
                        "transport": {
                            "type": "sqs",
                            "queue": (
                                "https://sqs.us-west-2.amazonaws.com/"
                                "619193117841/custodian-messages"),
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.poll()
        self.assertJmes('[]."c7n:MatchedFilters"', resources, [["tag:Testing"]])

    @functional
    def test_notify_region_var(self):
        session_factory = self.replay_flight_data("test_notify_region_var")

        ec2 = session_factory().resource("ec2")
        instance = ec2.create_instances(ImageId="ami-6057e21a", MinCount=1, MaxCount=1)[
            0
        ].id
        ec2_client = session_factory().client("ec2")
        ec2_client.create_tags(
            Resources=[instance], Tags=[{"Key": "k1", "Value": "v1"}]
        )
        self.addCleanup(ec2_client.terminate_instances, InstanceIds=[instance])

        sqs_client = session_factory().client("sqs")
        queue_url = sqs_client.create_queue(QueueName="c7n-test-q")["QueueUrl"]
        self.addCleanup(sqs_client.delete_queue, QueueUrl=queue_url)
        region_format = {"region": "us-east-1"}

        if self.recording:
            time.sleep(30)

        policy = self.load_policy(
            {
                "name": "instance-check",
                "resource": "ec2",
                "filters": [{"tag:k1": "v1"}],
                "actions": [
                    {
                        "type": "notify",
                        "to": ["someon@example.com"],
                        "transport": {
                            "type": "sqs",
                            "queue": "arn:aws:sqs:{region}:123456789012:c7n-test-q",
                        },
                    }
                ],
            },
            config={"region": "us-east-1"},
            session_factory=session_factory,
        )

        resources = policy.poll()
        self.assertJmes('[]."c7n:MatchedFilters"', resources, [["tag:k1"]])

        messages = sqs_client.receive_message(
            QueueUrl=queue_url.format(**region_format), AttributeNames=["All"]
        ).get(
            "Messages", []
        )
        self.assertEqual(len(messages), 1)
        body = json.loads(zlib.decompress(base64.b64decode(messages[0]["Body"])))
        self.assertTrue("tag:k1" in body.get("resources")[0].get("c7n:MatchedFilters"))
