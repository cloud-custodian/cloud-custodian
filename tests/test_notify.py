# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest, functional

import base64
import os
import json
import time
import tempfile
import zlib

from c7n.exceptions import PolicyValidationError
from c7n.actions.notify import ResourceMessageBuffer

import pytest


def test_msg_buffer():
    buf_size = 1024
    mbuffer = ResourceMessageBuffer({'env': 'dev', 'region': 'us-east-2'}, buf_size)
    assert mbuffer.full is False

    for i in range(0, 50):
        mbuffer.add({'id': 'x%s' % i, 'a': 1, 'b': 2 + i, 'c': 5 * i})
        if mbuffer.full:
            break

    assert len(mbuffer) == 47
    assert int(mbuffer.estimated_size) == 995
    payload = mbuffer.consume()
    assert len(payload) == 532
    assert mbuffer.observed_ratio > 0.36 and mbuffer.observed_ratio < 0.5
    assert 'resources' in json.loads(zlib.decompress(base64.b64decode(payload)))

    assert len(mbuffer) == 0
    # raw size reverts back to envelope
    assert mbuffer.raw_size == 56

    # repeat, but with observed dynamic ratio now
    for i in range(0, 100):
        mbuffer.add({'id': 'x%s' % i, 'a': 1, 'b': 2 + i, 'c': 5 * i})
        if mbuffer.full:
            break

    assert len(mbuffer) == 65
    payload = mbuffer.consume()
    assert len(payload) == 680


def test_msg_buffer_exceed():
    mbuffer = ResourceMessageBuffer({'env': 'dev', 'region': 'us-west-2'}, 100)
    assert mbuffer.full is False
    mbuffer.add({'id': 'x', 'values': list(range(100))})
    with pytest.raises(AssertionError) as e_info:
        mbuffer.consume()
    assert str(mbuffer) in str(e_info.value)


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
        temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        json.dump({"emails": ["me@example.com"]}, temp_file)
        temp_file.flush()

        self.addCleanup(os.unlink, temp_file.name)
        self.addCleanup(temp_file.close)

        url = "file:///%s" % temp_file.name.replace('\\', '/')

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
                            "url": url,
                            "format": "json",
                            "expr": "emails",
                        },
                        "cc_from": {
                            "url": url,
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
            {
                "account_id",
                "action",
                "event",
                "policy",
                "region",
                "account",
                "resources",
            },
        )

    # TODO refactor - extract method
    def test_resource_prep(self):
        policy = self.load_policy(
            {"name": "notify-sns",
             "resource": "ec2",
             "actions": [
                 {"type": "notify", "to": ["noone@example.com"],
                  "transport": {"type": "sns", "topic": "zebra"}}]})
        self.assertEqual(
            policy.resource_manager.actions[0].prepare_resources(
                [{'c7n:user-data': 'xyz', 'Id': 'i-123'}]),
            [{'Id': 'i-123'}])

        policy = self.load_policy(
            {"name": "notify-sns",
             "resource": "launch-config",
             "actions": [
                 {"type": "notify", "to": ["noone@example.com"],
                  "transport": {"type": "sns", "topic": "zebra"}}]})
        self.assertEqual(
            policy.resource_manager.actions[0].prepare_resources(
                [{'UserData': 'xyz', 'Id': 'l-123'}]),
            [{'Id': 'l-123'}])

        policy = self.load_policy(
            {"name": "notify-sns",
             "resource": "asg",
             "actions": [
                 {"type": "notify", "to": ["noone@example.com"],
                  "transport": {"type": "sns", "topic": "zebra"}}]})
        self.assertEqual(
            policy.resource_manager.actions[0].prepare_resources(
                [{'c7n:user-data': 'xyz', 'Id': 'a-123'}]),
            [{'Id': 'a-123'}])

        policy = self.load_policy(
            {"name": "notify-sns",
             "resource": "iam-saml-provider",
             "actions": [
                 {"type": "notify", "to": ["noone@example.com"],
                  "transport": {"type": "sns", "topic": "zebra"}}]})
        self.assertEqual(
            policy.resource_manager.actions[0].prepare_resources(
                [{'SAMLMetadataDocument': 'xyz', 'IDPSSODescriptor': 'abc', 'Id': 'a-123'}]),
            [{'Id': 'a-123'}])

    def test_sns_notify(self):
        session_factory = self.replay_flight_data("test_sns_notify_action")
        client = session_factory().client("sns", region_name='ap-northeast-2')
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
            config={'region': 'ap-northeast-2'}
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_sns_notify_with_msg_attr(self):
        session_factory = self.replay_flight_data("test_sns_notify_action_with_msg_attr")

        sqs = session_factory().client('sqs', region_name='us-east-1')
        sns = session_factory().client('sns', region_name='us-east-1')

        topic = 'arn:aws:sns:us-east-1:644160558196:test'

        policy = {
            "name": "notify-sns-with-attr",
            "resource": "sns",
            "actions": [
                {
                    "type": "notify",
                    "to": ["noone@example.com"],
                    "transport": {
                        "type": "sns",
                        "topic": topic,
                        "attributes": {"mtype": "test"}
                    },
                }
            ],
        }

        self.assertRaises(PolicyValidationError, self.load_policy, policy)

        policy['actions'][0]['transport']['attributes'] = {'good-attr': 'value'}

        self.assertTrue(self.load_policy(policy, validate=True))

        messages = sqs.receive_message(
            QueueUrl='https://sqs.us-east-1.amazonaws.com/644160558196/test-queue'
        ).get('Messages')
        self.assertFalse(messages)

        subscription = sns.list_subscriptions_by_topic(
            TopicArn=topic)['Subscriptions'][0]['Endpoint']
        self.assertEqual(subscription, 'arn:aws:sqs:us-east-1:644160558196:test-queue')

        self.load_policy(
            policy,
            session_factory=session_factory,
            config={'region': 'us-east-1'}
        ).run()
        if self.recording:
            time.sleep(20)

        message_body = json.loads(sqs.receive_message(
            QueueUrl='https://sqs.us-east-1.amazonaws.com/644160558196/test-queue'
        ).get('Messages')[0]['Body'])
        self.assertTrue('mtype' in message_body['MessageAttributes'])
        self.assertTrue('good-attr' in message_body['MessageAttributes'])

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

    def test_notify_region_queue(self):
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
                                "https://us-west-2.queue.amazonaws.com/"
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
