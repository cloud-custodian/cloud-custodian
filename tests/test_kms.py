# Copyright 2016-2017 Capital One Services, LLC
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

import json, time

from .common import BaseTest, functional


class KMSTest(BaseTest):

    def test_kms_grant(self):
        session_factory = self.replay_flight_data('test_kms_grants')
        p = self.load_policy(
            {'name': 'kms-grant-count',
             'resource': 'kms',
             'filters': [
                 {'type': 'grant-count'}]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_key_rotation(self):
        session_factory = self.replay_flight_data('test_key_rotation')
        p = self.load_policy(
            {'name': 'kms-key-rotation',
             'resource': 'kms-key',
             'filters': [
                 {'type': 'key-rotation-status', 'key': 'KeyRotationEnabled',
                  'value': False}]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 2)


    @functional
    def test_kms_remove_matched(self):
        session_factory = self.replay_flight_data('test_kms_remove_matched')
        client = session_factory().client('kms')
        key_id = client.create_key()['KeyMetadata']['KeyId']
        self.addCleanup(client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7)

        client.put_key_policy(
            KeyId=key_id,
            PolicyName='default',
            Policy=json.dumps({
                "Version": "2008-10-17",
                "Statement": [
                    {
                      "Sid": "DefaultRoot",
                      "Effect": "Allow",
                      "Principal": {
                        "AWS": "arn:aws:iam::123456789012:root"
                      },
                      "Action": "kms:*",
                      "Resource": "*"
                    },
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::123456789012:root"
                        },
                        "Action": [
                            "kms:*"
                        ]
                    },
                    {
                        "Sid": "Public",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": [
                            "kms:Put*"
                        ]
                    }
                ]
            })
        )

        p = self.load_policy({
            'name': 'kms-rm-matched',
            'resource': 'kms-key',
            'filters': [
                {'KeyId': key_id},
                {'type': 'cross-account',
                 'whitelist': ["123456789012"]}],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': 'matched'}]
            },
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual([r['KeyId'] for r in resources], [key_id])

        if self.recording:
            time.sleep(60) # takes time before new policy reflected

        data = json.loads(
            client.get_key_policy(
                KeyId=resources[0]['KeyId'],PolicyName='default').get('Policy'))
        self.assertEqual(
            [s['Sid'] for s in data.get('Statement', ())],
            ['DefaultRoot','SpecificAllow'])


    @functional
    def test_kms_remove_named(self):
        session_factory = self.replay_flight_data('test_kms_remove_named')
        client = session_factory().client('kms')
        key_id = client.create_key()['KeyMetadata']['KeyId']
        self.addCleanup(client.schedule_key_deletion, KeyId=key_id, PendingWindowInDays=7)

        client.put_key_policy(
            KeyId=key_id,
            PolicyName='default',
            Policy=json.dumps({
                "Version": "2008-10-17",
                "Statement": [
                    {
                      "Sid": "DefaultRoot",
                      "Effect": "Allow",
                      "Principal": {
                        "AWS": "arn:aws:iam::123456789012:root"
                      },
                      "Action": "kms:*",
                      "Resource": "*"
                    },
                    {
                        "Sid": "RemoveMe",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["kms:*"]
                    }
                ]
            })
        )

        p = self.load_policy({
            'name': 'kms-rm-named',
            'resource': 'kms-key',
            'filters': [{'KeyId': key_id}],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': ['RemoveMe']}]
            },
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)  

        if self.recording:
            time.sleep(60) # takes time before new policy reflected

        data = json.loads(
            client.get_key_policy(
                KeyId=resources[0]['KeyId'],PolicyName='default').get('Policy'))

        self.assertTrue('RemoveMe' not in [s['Sid'] for s in data.get('Statement', ())])
    