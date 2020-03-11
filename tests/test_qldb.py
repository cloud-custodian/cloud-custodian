# Copyright 2020 Cloud Custodian Authors
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
import time
from botocore.exceptions import ClientError
from .common import BaseTest


class TestQLDB(BaseTest):

    def test_qldb_describe(self):
        factory = self.replay_flight_data('test_qldb_describe')
        p = self.load_policy({
            'name': 'qldb', 'resource': 'aws.qldb'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual({r['Name'] for r in resources}, {'devledger', 'devx'})
        self.assertEqual(resources[0]['Tags'], [{'Key': 'Env', 'Value': 'Dev'}])

    def test_qldb_force_delete(self):
        factory = self.replay_flight_data('test_qldb_force_delete')
        p = self.load_policy({
            'name': 'qldb',
            'resource': 'aws.qldb',
            'actions': [{'type': 'delete', 'force': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'devledger')
        if self.recording:
            time.sleep(10)
        client = factory().client('qldb')
        self.assertRaises(
            ClientError, client.describe_ledger, Name='devledger')

    def test_qldb_delete(self):
        factory = self.replay_flight_data('test_qldb_delete')
        output = self.capture_logging('custodian.actions')
        p = self.load_policy({
            'name': 'qldb', 'resource': 'aws.qldb', 'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertIn('qldb delete found 1 delete-protected', output.getvalue())
        if self.recording:
            time.sleep(10)
        client = factory().client('qldb')
        self.assertRaises(
            ClientError, client.describe_ledger, Name='devx')
