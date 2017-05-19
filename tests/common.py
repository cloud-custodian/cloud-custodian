# Copyright 2016 Capital One Services, LLC
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
import StringIO
import shutil
import tempfile
import yaml
import unittest

from c7n import policy
from c7n.schema import generate, validate as schema_validate
from c7n.ctx import ExecutionContext
from c7n.resources import load_resources
from c7n.utils import CONN_CACHE

from .zpill import PillTest


logging.getLogger('placebo.pill').setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)


load_resources()

ACCOUNT_ID = '644160558196'

C7N_VALIDATE = bool(os.environ.get('C7N_VALIDATE', ''))
C7N_SCHEMA = generate()


skip_if_not_validating = unittest.skipIf(
    not C7N_VALIDATE, reason='We are not validating schemas.')

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
        suffix = "." + format
        file = tempfile.NamedTemporaryFile(suffix=suffix)
        if format == 'json':
            json.dump(policy, file)
        else:
            file.write(yaml.dump(policy, Dumper=yaml.SafeDumper))

        file.flush()
        self.addCleanup(file.close)
        return file.name

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
            e = Config.empty(**config)
        else:
            e = Config.empty()
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
            log_file = StringIO.StringIO()
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


def placebo_dir(name):
    return os.path.join(
        os.path.dirname(__file__), 'data', 'placebo', name)


def event_data(name):
    with open(
            os.path.join(
                os.path.dirname(__file__), 'data', 'cwe', name)) as fh:
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


class Bag(dict):

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class Config(Bag):

    @classmethod
    def empty(cls, **kw):
        region = os.environ.get('AWS_DEFAULT_REGION', "us-east-1")
        d = {}
        d.update({
            'region': region,
            'regions': [region],
            'cache': '',
            'profile': None,
            'account_id': ACCOUNT_ID,
            'assume_role': None,
            'external_id': None,
            'log_group': None,
            'metrics_enabled': False,
            'output_dir': 's3://test-example/foo',
            'cache_period': 0,
            'dryrun': False})
        d.update(kw)
        return cls(d)


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
