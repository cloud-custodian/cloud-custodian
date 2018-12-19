# Copyright 2015-2018 Capital One Services, LLC
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

import json
import logging
import os
import unittest
import uuid
from functools import partial

from c7n.schema import generate
from c7n.resources import load_resources
from c7n.config import Bag, Config

from c7n.testing import TestUtils, TextTestIO, functional # NOQA
from .zpill import PillTest


logging.getLogger("placebo.pill").setLevel(logging.DEBUG)
logging.getLogger("botocore").setLevel(logging.WARNING)


load_resources()

ACCOUNT_ID = "644160558196"


C7N_SCHEMA = generate()
C7N_VALIDATE = bool(os.environ.get("C7N_VALIDATE", ""))

skip_if_not_validating = unittest.skipIf(
    not C7N_VALIDATE, reason="We are not validating schemas."
)


class TestConfig(Config):
    config_args = {
        "metrics_enabled": False,
        "account_id": ACCOUNT_ID,
        "output_dir": "s3://test-example/foo",
    }

    empty = staticmethod(partial(Config.empty, **config_args))


# Set this so that if we run nose directly the tests will not fail
if "AWS_DEFAULT_REGION" not in os.environ:
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


class BaseTest(TestUtils, PillTest):

    custodian_schema = C7N_SCHEMA

    @property
    def account_id(self):
        return ACCOUNT_ID


class ConfigTest(BaseTest):
    """Test base class for integration tests with aws config.

    To allow for integration testing with config.

     - before creating and modifying use the
       initialize_config_subscriber method to setup an sqs queue on
       the config recorder's sns topic. returns the sqs queue url.

     - after creating/modifying a resource, use the wait_for_config
       with the queue url and the resource id.
    """

    def wait_for_config(self, session, queue_url, resource_id):
        # lazy import to avoid circular
        from c7n.sqsexec import MessageIterator

        client = session.client("sqs")
        messages = MessageIterator(client, queue_url, timeout=20)
        results = []
        while True:
            for m in messages:
                msg = json.loads(m["Body"])
                change = json.loads(msg["Message"])
                messages.ack(m)
                if change["configurationItem"]["resourceId"] != resource_id:
                    continue
                results.append(change["configurationItem"])
                break
            if results:
                break
        return results

    def initialize_config_subscriber(self, session):
        config = session.client("config")
        sqs = session.client("sqs")
        sns = session.client("sns")

        channels = config.describe_delivery_channels().get("DeliveryChannels", ())
        assert channels, "config not enabled"

        topic = channels[0]["snsTopicARN"]
        queue = "custodian-waiter-%s" % str(uuid.uuid4())
        queue_url = sqs.create_queue(QueueName=queue).get("QueueUrl")
        self.addCleanup(sqs.delete_queue, QueueUrl=queue_url)

        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=("Policy", "QueueArn")
        )
        queue_arn = attrs["Attributes"]["QueueArn"]
        policy = json.loads(
            attrs["Attributes"].get(
                "Policy",
                '{"Version":"2008-10-17","Id":"%s/SQSDefaultPolicy","Statement":[]}'
                % queue_arn,
            )
        )
        policy["Statement"].append(
            {
                "Sid": "ConfigTopicSubscribe",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "sqs:SendMessage",
                "Resource": queue_arn,
                "Condition": {"ArnEquals": {"aws:SourceArn": topic}},
            }
        )
        sqs.set_queue_attributes(
            QueueUrl=queue_url, Attributes={"Policy": json.dumps(policy)}
        )
        subscription = sns.subscribe(
            TopicArn=topic, Protocol="sqs", Endpoint=queue_arn
        ).get(
            "SubscriptionArn"
        )
        self.addCleanup(sns.unsubscribe, SubscriptionArn=subscription)
        return queue_url


def placebo_dir(name):
    return os.path.join(os.path.dirname(__file__), "data", "placebo", name)


def event_data(name, event_type="cwe"):
    with open(os.path.join(os.path.dirname(__file__), "data", event_type, name)) as fh:
        return json.load(fh)


def load_data(file_name, state=None, **kw):
    data = json.loads(
        open(os.path.join(os.path.dirname(__file__), "data", file_name)).read()
    )
    if state:
        data.update(state)
    if kw:
        data.update(kw)
    return data


def instance(state=None, file="ec2-instance.json", **kw):
    return load_data(file, state, **kw)


class Instance(Bag):
    pass


class Reservation(Bag):
    pass


class Client(object):

    def __init__(self, instances):
        self.instances = instances
        self.filters = None

    def get_all_instances(self, filters=None):
        self.filters = filters
        return [Reservation({"instances": [i for i in self.instances]})]
