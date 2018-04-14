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

import gzip
import logging
import mock
import unittest
import shutil
import os

from c7n.ctx import ExecutionContext
from c7n.output import S3Output

from .common import Bag, TestConfig as Config


class S3OutputTest(unittest.TestCase):

    def test_path_join(self):

        self.assertEqual(
            S3Output.join('s3://xyz/', '/bar/'),
            's3://xyz/bar')

        self.assertEqual(
            S3Output.join('s3://xyz/', '/bar/', 'foo'),
            's3://xyz/bar/foo')

        self.assertEqual(
            S3Output.join('s3://xyz/xyz/', '/bar/'),
            's3://xyz/xyz/bar')

    def get_s3_output(self):
        output = S3Output(
            ExecutionContext(
                None,
                Bag(name="xyz"),
                Config.empty(output_dir="s3://cloud-custodian/policies")))
        self.addCleanup(shutil.rmtree, output.root_dir)

        return output

    def test_s3_output(self):
        output = self.get_s3_output()
        self.assertEquals(output.use_s3(), True)

        # Make sure __repr__ is defined
        name = str(output)
        self.assertIn('bucket:cloud-custodian', name)

    def test_join_leave_log(self):
        output = self.get_s3_output()
        output.join_log()

        l = logging.getLogger('custodian.s3')

        # recent versions of nose mess with the logging manager
        v = l.manager.disable
        l.manager.disable = 0

        l.info('hello world')
        output.leave_log()
        logging.getLogger('c7n.s3').info('byebye')

        # Reset logging.manager back to nose configured value
        l.manager.disable = v

        with open(os.path.join(output.root_dir, "custodian-run.log")) as fh:
            content = fh.read().strip()
            self.assertTrue(content.endswith('hello world'))

    def test_compress(self):
        output = self.get_s3_output()

        with open(os.path.join(output.root_dir, 'foo.txt'), 'w') as fh:
            fh.write('abc')

        os.mkdir(os.path.join(output.root_dir, 'bucket'))
        with open(os.path.join(output.root_dir, 'bucket', 'here.log'), 'w') as fh:
            fh.write('abc')

        output.compress()
        for root, dirs, files in os.walk(output.root_dir):
            for f in files:
                self.assertTrue(f.endswith('.gz'))

                with gzip.open(os.path.join(root, f)) as fh:
                    self.assertEqual(fh.read(), b'abc')

    def test_upload(self):
        output = self.get_s3_output()
        self.assertEqual(output.key_prefix, "/policies/xyz")

        with open(os.path.join(output.root_dir, 'foo.txt'), 'w') as fh:
            fh.write('abc')

        output.transfer = mock.MagicMock()
        output.transfer.upload_file = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            fh.name, 'cloud-custodian',
            'policies/xyz/%s/foo.txt' % output.date_path ,
            extra_args={
                'ServerSideEncryption': 'AES256'})

    def test_sans_prefix(self):
        output = self.get_s3_output()

        with open(os.path.join(output.root_dir, 'foo.txt'), 'w') as fh:
            fh.write('abc')

        output.transfer = mock.MagicMock()
        output.transfer.upload_file = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            fh.name, 'cloud-custodian',
            'policies/xyz/%s/foo.txt' % output.date_path,
            extra_args={
                'ServerSideEncryption': 'AES256'})
