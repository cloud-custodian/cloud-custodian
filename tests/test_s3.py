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
import shutil
import tempfile
from unittest import TestCase

from c7n.resources import s3

from common import BaseTest


class RestoreCompletionTest(TestCase):

    def test_restore_complete(self):

        self.assertTrue(
            s3.restore_complete(
                ('ongoing-request="false", '
                 'expiry-date="Fri, 23 Dec 2012 00:00:00 GMT"')))

        self.assertFalse(s3.restore_complete('ongoing-request="true"'))
    

class BucketScanLogTests(TestCase):

    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.log_dir)
        self.log = s3.BucketScanLog(self.log_dir, 'test')
        
    def test_scan_log(self):
        with self.log:
            self.log.add(range(10)[:5])
            self.log.add(range(10)[5:])

        with open(self.log.path) as fh:
            data = json.load(fh)
            self.assertEqual(
                data,
                [range(10)[:5], range(10)[5:], []])


class S3Test(BaseTest):

    def test_global_grants_filter_and_remove(self):
        self.patch(s3, 'S3_AUGMENT_TABLE', [
            ('get_bucket_acl', 'Acl', None, None)
            ])
        session_factory = self.replay_flight_data('test_s3_grants')

        bname = 'custodian-testing-grants'
        session = session_factory()
        client = session.client('s3')
        client.create_bucket(Bucket=bname)
        public = 'http://acs.amazonaws.com/groups/global/AllUsers'
        client.put_bucket_acl(
            Bucket=bname,
            AccessControlPolicy={
                "Owner": {
                    "DisplayName": "k_vertigo",
                    "ID": "904fc4c4790937100e9eb293a15e6a0a1f265a064888055b43d030034f8881ee"
                },
                'Grants': [
                    {'Grantee': {
                        'Type': 'Group',
                        'URI': public},
                     'Permission': 'WRITE'}
                    ]})
        p = self.load_policy(
            {'name': 's3-remove-global',
             'resource': 's3',
             'filters': [
                 {'Name': 'custodian-testing-grants'},
                 {'type': 'global-grants'}],
             'actions': [
                 {'type': 'delete-global-grants',
                  'grantees': [public]}]
             }, session_factory=session_factory)
        resources = p.run()
        grants = client.get_bucket_acl(Bucket=bname)
        client.delete_bucket(Bucket=bname)
        self.assertEqual(grants['Grants'], [])
        self.assertEqual(resources[0]['Name'], bname)


