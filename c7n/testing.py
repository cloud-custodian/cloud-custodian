# Copyright 2018 Capital One Services, LLC
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
import io
import logging
import os
import shutil
import tempfile
import unittest

import six
import yaml

from c7n import policy
from c7n.schema import validate as schema_validate
from c7n.ctx import ExecutionContext
from c7n.utils import CONN_CACHE
from c7n.config import Bag, Config

C7N_VALIDATE = bool(os.environ.get("C7N_VALIDATE", ""))

skip_if_not_validating = unittest.skipIf(
    not C7N_VALIDATE, reason="We are not validating schemas."
)


try:
    import pytest

    functional = pytest.mark.functional
except ImportError:
    functional = lambda func: func  # noqa E731


class TestUtils(unittest.TestCase):

    custodian_schema = None

    def tearDown(self):
        self.cleanUp()

    def cleanUp(self):
        # Clear out thread local session cache
        CONN_CACHE.session = None

    def write_policy_file(self, policy, format="yaml"):
        """ Write a policy file to disk in the specified format.

        Input a dictionary and a format. Valid formats are `yaml` and `json`
        Returns the file path.
        """
        fh = tempfile.NamedTemporaryFile(mode="w+b", suffix="." + format)
        if format == "json":
            fh.write(json.dumps(policy).encode("utf8"))
        else:
            fh.write(yaml.dump(policy, encoding="utf8", Dumper=yaml.SafeDumper))

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
            session_factory, policy or Bag({"name": "test-policy"}), config
        )
        return ctx

    def load_policy(
        self,
        data,
        config=None,
        session_factory=None,
        validate=C7N_VALIDATE,
        output_dir=None,
        cache=False,
    ):
        if validate:
            errors = schema_validate({"policies": [data]}, self.custodian_schema)
            if errors:
                raise errors[0]

        config = config or {}
        if not output_dir:
            temp_dir = self.get_temp_dir()
            config["output_dir"] = temp_dir
        if cache:
            config["cache"] = os.path.join(temp_dir, "c7n.cache")
            config["cache_period"] = 300
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

    def change_cwd(self, work_dir=None):
        if work_dir is None:
            work_dir = self.get_temp_dir()

        cur_dir = os.path.abspath(os.getcwd())

        def restore():
            os.chdir(cur_dir)

        self.addCleanup(restore)

        os.chdir(work_dir)
        return work_dir

    def change_environment(self, **kwargs):
        """Change the environment to the given set of variables.

        To clear an environment variable set it to None.
        Existing environment restored after test.
        """
        # preserve key elements needed for testing
        for env in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]:
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
                del (kwargs[key])
        os.environ.update(kwargs)

    def capture_logging(
        self, name=None, level=logging.INFO, formatter=None, log_file=None
    ):
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


class TextTestIO(io.StringIO):

    def write(self, b):

        # print handles both str/bytes and unicode/str, but io.{String,Bytes}IO
        # requires us to choose. We don't have control over all of the places
        # we want to print from (think: traceback.print_exc) so we can't
        # standardize the arg type up at the call sites. Hack it here.

        if not isinstance(b, six.text_type):
            b = b.decode("utf8")
        return super(TextTestIO, self).write(b)
