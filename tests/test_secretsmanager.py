# Copyright 2016-2018 Capital One Services, LLC
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
from .common import BaseTest, functional

import time

class TestSecretsManager(BaseTest):

    def test_secrets_manager_resource(self):
        session = self.replay_flight_data('test_secrets_manager_resource')
        client = session(region='us-east-1').client('secretsmanager')
        p = self.load_policy({
            'name': 'secrets-manager-resource',
            'resource': 'secrets-manager'}, session_factory=session)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0].get('Versions'))

    def test_secrets_manager_tag_resource(self):
        session = self.replay_flight_data('test_tag_secrets_manager_resource')
        client = session(region='us-east-1').client('secretsmanager')
        og_tags = client.describe_secret(
                SecretId='c7n-test-key').get('Tags')
        self.assertFalse(og_tags)
        p = self.load_policy({
            'name': 'secrets-manager-resource',
            'resource': 'secrets-manager',
            'actions': [
                {'type': 'tag',
                'key': 'new-tag',
                'value': 'new-value'}
                ]
            },
            session_factory=session)
        resources = p.run()
        new_tags = resources[0]['Tags']
        self.assertEqual(len(new_tags), 1)
        self.assertEqual(new_tags[0].get('Key'), 'new-tag')

        p = self.load_policy({
            'name': 'secrets-manager-resource',
            'resource': 'secrets-manager',
            'actions': [
                {'type': 'remove-tag',
                'tags': ['new-tag']}
                ]
            },
            session_factory=session)
        resources = p.run()
        new_tags = resources[0]['Tags']
        new_tags = client.describe_secret(
                SecretId='c7n-test-key').get('Tags')
        self.assertEqual(len(new_tags), 0)
