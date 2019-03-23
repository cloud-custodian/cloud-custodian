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

import datetime
import gzip
import logging
import mock
import shutil
import io
import json
import os
import pytest

from dateutil.parser import parse as date_parse

from c7n.ctx import ExecutionContext
from c7n.output import DirectoryOutput, LogFile, metrics_outputs, JSONFormatter
from c7n.resources.aws import S3Output, MetricsOutput
from c7n.testing import mock_datetime_now, TestUtils

from .common import Bag, BaseTest, TestConfig as Config


class MetricsTest(BaseTest):

    def test_boolean_config_compatibility(self):
        self.assertTrue(
            isinstance(metrics_outputs.select(True, {}), MetricsOutput))


class DirOutputTest(BaseTest):

    def get_dir_output(self, location):
        work_dir = self.change_cwd()
        return work_dir, DirectoryOutput(
            ExecutionContext(
                None,
                Bag(name="xyz", provider_name="ostack"),
                Config.empty(output_dir=location)),
            {'url': location},
        )

    def test_dir_output(self):
        work_dir, output = self.get_dir_output("file://myoutput")
        self.assertEqual(os.listdir(work_dir), ["myoutput"])
        self.assertTrue(os.path.isdir(os.path.join(work_dir, "myoutput")))


class S3OutputTest(TestUtils):

    def test_path_join(self):

        self.assertEqual(S3Output.join("s3://xyz/", "/bar/"), "s3://xyz/bar")

        self.assertEqual(S3Output.join("s3://xyz/", "/bar/", "foo"), "s3://xyz/bar/foo")

        self.assertEqual(S3Output.join("s3://xyz/xyz/", "/bar/"), "s3://xyz/xyz/bar")

    def get_s3_output(self):
        output_dir = "s3://cloud-custodian/policies"
        output = S3Output(
            ExecutionContext(
                None,
                Bag(name="xyz", provider_name="ostack"),
                Config.empty(output_dir=output_dir)),
            {'url': output_dir})

        self.addCleanup(shutil.rmtree, output.root_dir)

        return output

    def test_s3_output(self):
        output = self.get_s3_output()
        self.assertEqual(output.type, "s3")

        # Make sure __repr__ is defined
        name = str(output)
        self.assertIn("bucket:cloud-custodian", name)

    def test_join_leave_log(self):
        temp_dir = self.get_temp_dir()
        output = LogFile(Bag(log_dir=temp_dir, options={}), {})
        output.join_log()

        l = logging.getLogger("custodian.s3")  # NOQA

        # recent versions of nose mess with the logging manager
        v = l.manager.disable
        l.manager.disable = 0

        l.info("hello world")
        output.leave_log()
        logging.getLogger("c7n.s3").info("byebye")

        # Reset logging.manager back to nose configured value
        l.manager.disable = v

        with open(os.path.join(temp_dir, "custodian-run.log")) as fh:
            content = fh.read().strip()
            self.assertTrue(content.endswith("hello world"))

    def test_compress(self):
        output = self.get_s3_output()

        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        os.mkdir(os.path.join(output.root_dir, "bucket"))
        with open(os.path.join(output.root_dir, "bucket", "here.log"), "w") as fh:
            fh.write("abc")

        output.compress()
        for root, dirs, files in os.walk(output.root_dir):
            for f in files:
                self.assertTrue(f.endswith(".gz"))

                with gzip.open(os.path.join(root, f)) as fh:
                    self.assertEqual(fh.read(), b"abc")

    def test_upload(self):

        with mock_datetime_now(date_parse('2018/09/01 13:00'), datetime):
            output = self.get_s3_output()
            self.assertEqual(output.key_prefix, "/policies/xyz/2018/09/01/13")

        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        output.transfer = mock.MagicMock()
        output.transfer.upload_file = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            fh.name,
            "cloud-custodian",
            "%s/foo.txt" % output.key_prefix.lstrip('/'),
            extra_args={"ACL": "bucket-owner-full-control", "ServerSideEncryption": "AES256"},
        )

    def test_sans_prefix(self):
        output = self.get_s3_output()

        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        output.transfer = mock.MagicMock()
        output.transfer.upload_file = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            fh.name,
            "cloud-custodian",
            "%s/foo.txt" % output.key_prefix.lstrip('/'),
            extra_args={"ACL": "bucket-owner-full-control", "ServerSideEncryption": "AES256"},
        )


test_cases = [
    ('policy policy',
     {'type': 'log', 'logger': 'test-logger', 'level': 'INFO', 'module': 'test_output',
      'msg': {'original': 'policy policy'}}),
    ('policy:test_policy id:123',
     {'type': 'log', 'logger': 'test-logger', 'level': 'INFO', 'module': 'test_output',
      'msg': {'original': 'policy:test_policy id:123', 'policy': 'test_policy', 'id': 123}}),
    ('policy: not a policy',
     {'level': 'INFO', 'logger': 'test-logger', 'module': 'test_output',
      'msg': {'original': 'policy: not a policy', 'policy': ''}, 'type': 'log'}),
    ("ids:['xyz','abc','def']",
     {'type': 'log', 'logger': 'test-logger', 'level': 'INFO', 'module': 'test_output',
      'msg': {'ids': ['xyz', 'abc', 'def'], 'original': "ids:['xyz','abc','def']"}}),
]


@pytest.mark.parametrize("input_log,expected_output", test_cases)
def test_convert_to_json(input_log, expected_output):
    logger = logging.getLogger('test-logger')
    logger.setLevel(logging.DEBUG)

    # python 2 uses StringIO
    try:
        from StringIO import StringIO
        stream = StringIO.StringIO()
    except ImportError:
        stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    logger.info(input_log)
    log_contents = stream.getvalue()

    stream.close()
    logger.removeHandler(handler)

    json_log = json.loads(log_contents)
    if json_log.get("log_time"):
        del json_log["log_time"]

    assert json_log == expected_output
