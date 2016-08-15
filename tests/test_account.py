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

    def test_service_limit(self):
        session_factory = self.replay_flight_data('test_account_service_limit')
        p = self.load_policy({
            'name': 'service-limit',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'threshold': 0}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['ServiceLimitsExceeded']), 50)

    def test_service_limit_specific_check(self):
        session_factory = self.replay_flight_data('test_account_service_limit')
        p = self.load_policy({
            'name': 'service-limit',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'limits': ['DB security groups'],
                'threshold': 1.0
            }]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            set([l['service'] for l in resources[0]['ServiceLimitsExceeded']]),
            set(['RDS']))
        self.assertEqual(
            set([l['region'] for l in resources[0]['ServiceLimitsExceeded']]),
            set(['us-east-1', 'us-west-2', 'us-west-1']))
        self.assertEqual(
            set([l['check'] for l in resources[0]['ServiceLimitsExceeded']]),
            set(['DB security groups']))
        self.assertEqual(len(resources[0]['ServiceLimitsExceeded']), 3)

    def test_service_limit_specific_service(self):
        session_factory = self.replay_flight_data('test_account_service_limit')
        p = self.load_policy({
            'name': 'service-limit',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit', 'services': ['IAM'], 'threshold': 1.0
            }]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            set([l['service'] for l in resources[0]['ServiceLimitsExceeded']]),
            set(['IAM']))
        self.assertEqual(len(resources[0]['ServiceLimitsExceeded']), 2)

    def test_service_limit_no_threshold(self):
        # only warns when the default threshold goes to warning or above
        session_factory = self.replay_flight_data('test_account_service_limit')
        p = self.load_policy({
            'name': 'service-limit',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)


