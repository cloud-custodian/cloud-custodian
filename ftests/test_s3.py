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

from botocore.exceptions import ClientError
import boto3

import os
import shutil
import subprocess
import tempfile
import unittest


from c7n.resources.s3 import S3, EncryptExtantKeys, EncryptedPrefix

from c7n.tests.common import BaseTest, Config, Bag


TEST_S3_BUCKET = os.environ.get('TEST_BUCKET', "cloud-c7n-ftest")


def session_factory():
    # Use environment variables for standard configuration
    # http://boto3.readthedocs.org/en/latest/guide/configuration.html#environment-variables
    return boto3.Session()


def initialize_layer_s3():
    s = session_factory().client('s3')
    s.get_bucket(Bucket=TEST_S3_BUCKET)


def generateBucketContents(s3, bucket, contents):
    b = s3.Bucket(bucket)
    for k, v in contents.items():
        key = s3.Object(bucket, k)
        key.put(
            Body=v,
            ContentLength=len(v),
            ContentType='text/plain')
    

class S3Functional(BaseTest):

    def setUp(self):
        self.session = session_factory()
        self.client = self.session.client('s3')
        self.s3 = self.session.resource('s3')
        self.b = TEST_S3_BUCKET

        try:
            self.client.get_bucket_acl(Bucket=self.b)
        except ClientError, e:
            if e.response['Error']['Code'] != 'NoSuchBucket':
                raise
            self.client.create_bucket(Bucket=self.b)
        else:
            raise ValueError("Test Bucket %s already exists" % self.b)

        self.log_dir = tempfile.mkdtemp()
        
        self.addCleanup(shutil.rmtree, self.log_dir)
        self.output = self.capture_logging('maid')
        self.manager = S3(
            self.get_context(
                session_factory=session_factory,
                policy=Bag({'name': 'cloud-maid-s3-ftest',
                            'resource_type': 's3'}),
                config=Config.empty(output_dir=self.log_dir)),
            {})
        
    def generate_contents(self, contents=None):
        default_contents = {
            'home.txt': 'hello',
            'AWSLogs/2015/10/10': 'out',
            'AWSLogs/2015/10/11': 'spot'}
        if contents is None:
            contents = default_contents
        generateBucketContents(
            self.s3, self.b, contents)

    def tearDown(self):
        subprocess.check_output(
            ['aws', 's3', 'rb', '--force', "s3://%s" % self.b])

    def test_encrypted_prefix(self):
        #
        # Creating a prefix for logs. 
        #
        # So this is a confirmation that encrypting a prefix key does nothing for
        # either previous objects or new objects under that prefix :-(

        self.generate_contents()
        manager = self.manager
        visitor = EncryptedPrefix({'prefix': 'AWSLogs'}, manager, self.log_dir)
        result = visitor.process([{"Name": self.b}])
        self.assertEqual(
            result,
            [{'Bucket': self.b, 'Prefix': 'AWSLogs', 'State': 'Created'}])

        # Verify prefix is encrypted
        self.assertTrue(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key='AWSLogs'))
        
        prefix_check_path = 'AWSLogs/xyz.txt'
        # new objects we add should be encrypted
        self.client.put_object(
            Bucket=self.b,
            Key=prefix_check_path,
            Body='hello cruel world',
            ACL="bucket-owner-full-control")

        # Previous object still unencrypted
        self.assertFalse(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key='AWSLogs/2015/10/10'))

        # New object still unecrypted
        self.assertFalse(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key=prefix_check_path))
        
    def test_bucket_scan_empty_bucket(self):
        manager = self.manager
        visitor = EncryptExtantKeys({'report-only': True}, manager, self.log_dir)
        result = visitor.process([{"Name": self.b}])
        # Assert that we get the right remediated counts
        self.assertEqual(
            result, [{'Count': 0, 'Remediated': 0, 'Bucket': 'cloud-maid-ftest'}])
        
    def test_encrypt_keys_read_only(self):
        self.generate_contents()
        manager = self.manager
        visitor = EncryptExtantKeys({'report-only': True}, manager, self.log_dir)
        result = visitor.process([{"Name": self.b}])

        self.assertEqual(
            result, [{'Count': 3, 'Remediated': 3, 'Bucket': self.b}])

        # Assert that we get the right remediated counts in the log
        self.assertTrue(
            "keys:3 remediated:3" in self.output.getvalue())

        # And that we didn't actually modify the object
        self.assertFalse(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key='home.txt'))
        
    def test_encrypt_keys(self):
        self.generate_contents()
        manager = self.manager
        visitor = EncryptExtantKeys({}, manager, self.log_dir)
        result = visitor.process([{"Name": self.b}])
        self.assertEqual(
            result, [{'Count': 3, 'Remediated': 3, 'Bucket': self.b}])

        # Assert that we get the right remediated counts in the log
        self.assertTrue(
            "keys:3 remediated:3" in self.output.getvalue())
        self.assertTrue(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key='home.txt'))

    def test_encrypt_keys_kms(self):
        self.generate_contents()

        manager = self.manager
        visitor = EncryptExtantKeys({'crypto': 'aws:kms'}, manager, self.log_dir)
        result = visitor.process([{"Name": self.b}])

        self.assertEqual(
            result, [{'Count': 3, 'Remediated': 3, 'Bucket': self.b}])
        
        # Assert that we get the right remediated counts in the log
        self.assertTrue(
            "keys:3 remediated:3" in self.output.getvalue())
        self.assertTrue(
            'ServerSideEncryption' in self.client.head_object(
                Bucket=self.b, Key='home.txt'))

    
if __name__ == '__main__':
    unittest.main()


