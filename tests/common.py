# Copyright 2015-2017 Capital One Services, LLC
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

import boto3
import io
import json
import logging
import os
import shutil
import tempfile
import unittest
import uuid
from functools import partial

import six
import yaml

from c7n import policy
from c7n.filters import revisions
from c7n.schema import generate, validate as schema_validate
from c7n.ctx import ExecutionContext
from c7n.resources import load_resources
from c7n.utils import CONN_CACHE
from c7n.config import Bag, Config

from .zpill import PillTest


logging.getLogger('placebo.pill').setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)


load_resources()

ACCOUNT_ID = '644160558196'

C7N_VALIDATE = bool(os.environ.get('C7N_VALIDATE', ''))
C7N_SCHEMA = generate()

skip_if_not_validating = unittest.skipIf(
    not C7N_VALIDATE, reason='We are not validating schemas.')

class TestConfig(Config):
    config_args = {
        "metrics_enabled": False,
        "account_id": ACCOUNT_ID,
        "output_dir": "s3://test-example/foo"
    }

    empty = staticmethod(partial(Config.empty, **config_args))

# Set this so that if we run nose directly the tests will not fail
if 'AWS_DEFAULT_REGION' not in os.environ:
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


class BaseTest(PillTest):

    def cleanUp(self):
        # Clear out thread local session cache
        CONN_CACHE.session = None

    def write_policy_file(self, policy, format='yaml'):
        """ Write a policy file to disk in the specified format.

        Input a dictionary and a format. Valid formats are `yaml` and `json`
        Returns the file path.
        """
        fh = tempfile.NamedTemporaryFile(mode='w+b', suffix='.' + format)
        if format == 'json':
            fh.write(json.dumps(policy).encode('utf8'))
        else:
            fh.write(yaml.dump(policy, encoding='utf8', Dumper=yaml.SafeDumper))

        fh.flush()
        self.addCleanup(fh.close)
        return fh.name

    def get_temp_dir(self):
        """ Return a temporary directory that will get cleaned up. """
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        return temp_dir

    def get_context(self, config=None, session_factory=None, policy=None):
        if config is None:
            self.context_output_dir = self.get_temp_dir()
            config = Config.empty(output_dir=self.context_output_dir)
        ctx = ExecutionContext(
            session_factory,
            policy or Bag({'name': 'test-policy'}),
            config)
        return ctx

    def load_policy(
            self, data, config=None, session_factory=None,
            validate=C7N_VALIDATE, output_dir=None, cache=False):
        if validate:
            errors = schema_validate({'policies': [data]}, C7N_SCHEMA)
            if errors:
                raise errors[0]

        config = config or {}
        if not output_dir:
            temp_dir = self.get_temp_dir()
            config['output_dir'] = temp_dir
        if cache:
            config['cache'] = os.path.join(temp_dir, 'c7n.cache')
            config['cache_period'] = 300
        conf = Config.empty(**config)
        p = policy.Policy(data, conf, session_factory)
        p.validate()
        return p

    def load_policy_set(self, data, config=None):
        filename = self.write_policy_file(data)
        if config:
            config['account_id'] = ACCOUNT_ID
            e = Config.empty(**config)
        else:
            e = Config.empty(account_id=ACCOUNT_ID)
        return policy.load(e, filename)

    def patch(self, obj, attr, new):
        old = getattr(obj, attr, None)
        setattr(obj, attr, new)
        self.addCleanup(setattr, obj, attr, old)

    def change_environment(self, **kwargs):
        """Change the environment to the given set of variables.

        To clear an environment variable set it to None.
        Existing environment restored after test.
        """
        # preserve key elements needed for testing
        for env in ["AWS_ACCESS_KEY_ID",
                    "AWS_SECRET_ACCESS_KEY",
                    "AWS_DEFAULT_REGION"]:
            if env not in kwargs:
                kwargs[env] = os.environ.get(env, "")

        original_environ = dict(os.environ)

        @self.addCleanup
        def cleanup_env():
            os.environ.clear()
            os.environ.update(original_environ)

        os.environ.clear()
        for key, value in kwargs.items():
            if value is None:
                del(kwargs[key])
        os.environ.update(kwargs)

    def capture_logging(
            self, name=None, level=logging.INFO,
            formatter=None, log_file=None):
        if log_file is None:
            log_file = TextTestIO()
        log_handler = logging.StreamHandler(log_file)
        if formatter:
            log_handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.addHandler(log_handler)
        old_logger_level = logger.level
        logger.setLevel(level)

        @self.addCleanup
        def reset_logging():
            logger.removeHandler(log_handler)
            logger.setLevel(old_logger_level)

        return log_file

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
        client = session.client('sqs')
        messages = MessageIterator(client, queue_url, timeout=20)
        results = []
        while True:
            for m in messages:
                msg = json.loads(m['Body'])
                change = json.loads(msg['Message'])
                messages.ack(m)
                if change['configurationItem']['resourceId'] != resource_id:
                    continue
                results.append(change['configurationItem'])
                break
            if results:
                break
        return results

    def initialize_config_subscriber(self, session):
        config = session.client('config')
        sqs = session.client('sqs')
        sns = session.client('sns')

        channels = config.describe_delivery_channels().get('DeliveryChannels', ())
        assert channels, "config not enabled"

        topic = channels[0]['snsTopicARN']
        queue = "custodian-waiter-%s" % str(uuid.uuid4())
        queue_url = sqs.create_queue(QueueName=queue).get('QueueUrl')
        self.addCleanup(sqs.delete_queue, QueueUrl=queue_url)

        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=('Policy', 'QueueArn'))
        queue_arn = attrs['Attributes']['QueueArn']
        policy = json.loads(attrs['Attributes'].get(
            'Policy',
            '{"Version":"2008-10-17","Id":"%s/SQSDefaultPolicy","Statement":[]}' % queue_arn))
        policy['Statement'].append({
            "Sid": "ConfigTopicSubscribe",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "sqs:SendMessage",
            "Resource": queue_arn,
            "Condition": {
                "ArnEquals": {
                    "aws:SourceArn": topic}}})
        sqs.set_queue_attributes(
            QueueUrl=queue_url, Attributes={'Policy': json.dumps(policy)})
        subscription = sns.subscribe(
            TopicArn=topic, Protocol='sqs', Endpoint=queue_arn).get(
                'SubscriptionArn')
        self.addCleanup(sns.unsubscribe, SubscriptionArn=subscription)
        return queue_url


class TextTestIO(io.StringIO):

    def write(self, b):

        # print handles both str/bytes and unicode/str, but io.{String,Bytes}IO
        # requires us to choose. We don't have control over all of the places
        # we want to print from (think: traceback.print_exc) so we can't
        # standardize the arg type up at the call sites. Hack it here.

        if not isinstance(b, six.text_type):
            b = b.decode('utf8')
        return super(TextTestIO, self).write(b)


def placebo_dir(name):
    return os.path.join(
        os.path.dirname(__file__), 'data', 'placebo', name)


def event_data(name, event_type='cwe'):
    with open(
            os.path.join(
                os.path.dirname(__file__), 'data', event_type, name)) as fh:
        return json.load(fh)


def load_data(file_name, state=None, **kw):
    data = json.loads(open(
        os.path.join(
            os.path.dirname(__file__), 'data',
            file_name)).read())
    if state:
        data.update(state)
    if kw:
        data.update(kw)
    return data


def instance(state=None, file='ec2-instance.json', **kw):
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
        return [Reservation(
            {'instances': [i for i in self.instances]})]


try:
    import pytest
    functional = pytest.mark.functional
except ImportError:
    functional = lambda func: func  # noop
