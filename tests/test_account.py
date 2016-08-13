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
from common import BaseTest


class AccountTests(BaseTest):

    def test_root_mfa_enabled(self):
        session_factory = self.replay_flight_data('test_account_root_mfa')
        p = self.load_policy({
            'name': 'root-mfa',
            'resource': 'account',
            'filters': [
                {'type': 'iam-summary',
                 'key': 'AccountMFAEnabled', 'value': False}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_root_api_keys(self):
        session_factory = self.replay_flight_data('test_account_root_api_keys')
        p = self.load_policy({
            'name': 'root-api',
            'resource': 'account',
            'filters': [
                {'type': 'iam-summary'}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)        
        
    def test_cloudtrail_enabled(self):
        session_factory = self.replay_flight_data('test_account_trail')
        p = self.load_policy({
            'name': 'trail-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'check-cloudtrail',
                 'multi-region': True,
                 'kms': True,
                 'file-digest': True,
                 'global-events': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_notifies(self):
        session_factory = self.replay_flight_data('test_account_trail')
        p = self.load_policy({
            'name': 'trail-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'check-cloudtrail',
                 'notifies': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        
    def test_config_enabled(self):
        session_factory = self.replay_flight_data('test_account_config')
        p = self.load_policy({
            'name': 'config-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'check-config',
                 'all-resources': True,
                 'running': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_config_enabled_global(self):
        session_factory = self.replay_flight_data('test_account_config_global')
        p = self.load_policy({
            'name': 'config-enabled',
            'resource': 'account',
            'filters': [
                {'type': 'check-config',
                 'global-resources': True}
            ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)        
        
