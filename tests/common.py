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
import json
import logging
import os
import StringIO
import shutil
import tempfile
import yaml

from c7n import policy
from c7n.ctx import ExecutionContext
from c7n.resources import load_resources
from c7n.utils import CONN_CACHE

from zpill import PillTest


logging.getLogger('placebo.pill').setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)


load_resources()


class BaseTest(PillTest):

    def cleanUp(self):
        # Clear out thread local session cache
        CONN_CACHE.session = None

    def get_context(self, config=None, session_factory=None, policy=None):
        if config is None:
            self.context_output_dir = self.mkdtemp()
            self.addCleanup(shutil.rmtree, self.context_output_dir)
            config = Config.empty(output_dir=self.context_output_dir)
        ctx = ExecutionContext(
            session_factory,
            policy or Bag({'name':'test-policy'}),
            config)
        return ctx

    def load_policy(self, data, config=None, session_factory=None):
        config = config or {}
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)
        config['output_dir'] = temp_dir
        conf = Config.empty(**config)
        return policy.Policy(data, conf, session_factory)

    def load_policy_set(self, data, config=None):
        t = tempfile.NamedTemporaryFile()
        t.write(yaml.dump(data, Dumper=yaml.SafeDumper))
        t.flush()
        self.addCleanup(t.close)
        if config:
            e = Config.empty(**config)
        else:
            e = Config.empty()
        return policy.load(e, t.name)

    def patch(self, obj, attr, new):
        old = getattr(obj, attr, None)
        setattr(obj, attr, new)
        self.addCleanup(setattr, obj, attr, old)

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


def instance(state=None, **kw):
    return load_data('ec2-instance.json', state, **kw)


class Bag(dict):

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class Config(Bag):

    @classmethod
    def empty(cls, **kw):
        d = {}
        d.update({
            'region': os.environ.get('AWS_DEFAULT_REGION', "us-east-1"),
            'cache': '',
            'profile': None,
            'assume_role': None,
            'log_group': None,
            'metrics_enabled': False,
            'output_dir': 's3://test-example/foo',
            'cache_period': 0,
            'dryrun': False})
        d.update(kw)
        return cls(d)


class Instance(Bag): pass


class Reservation(Bag): pass


class Client(object):

    def __init__(self, instances):
        self.instances = instances
        self.filters = None

    def get_all_instances(self, filters=None):
        self.filters = filters
        return [Reservation(
            {'instances': [i for i in self.instances]})]
