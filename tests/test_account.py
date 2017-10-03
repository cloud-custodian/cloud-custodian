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

from .common import BaseTest
from c7n.executor import MainThreadExecutor
from c7n.utils import local_session
from c7n.filters import FilterValidationError
from jsonschema.exceptions import ValidationError


import datetime
from dateutil import parser

from .test_offhours import mock_datetime_now
from .common import Config, functional

TRAIL = 'nosetest'


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

    def test_cloudtrail_current_region_global(self):
        session_factory = self.replay_flight_data('test_account_trail')
        p = self.load_policy({
            'name': 'trail-global',
            'resource': 'account',
            'filters': [
                {'type': 'check-cloudtrail',
                 'current-region': True,
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_current_region_specific_same(self):
        session_factory = self.replay_flight_data('test_account_trail_same_region')
        p = self.load_policy({
            'name': 'trail-same-region',
            'resource': 'account',
            'filters': [
                {'type': 'check-cloudtrail',
                 'current-region': True,
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_current_region_specific_same(self):
        session_factory = self.replay_flight_data('test_account_trail_different_region')
        p = self.load_policy({
            'name': 'trail-different-region',
            'resource': 'account',
            'filters': [
                {'type': 'check-cloudtrail',
                 'current-region': True,
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

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

    def test_credential_report(self):
        session_factory = self.replay_flight_data('test_account_credential_report')
        p = self.load_policy({
            'name': 'credential-details',
            'resource': 'account',
            'filters': [
                {'type': 'credential',
                 'key': 'mfa_active',
                 'value': True}
            ]}, session_factory=session_factory)
        with mock_datetime_now(
                parser.parse('2017-02-23T00:40:00+00:00'), datetime):
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
        self.assertEqual(len(resources[0]['c7n:ServiceLimitsExceeded']), 10)

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
            set([l['service'] for l
                 in resources[0]['c7n:ServiceLimitsExceeded']]),
            set(['RDS']))
        self.assertEqual(
            set([l['region'] for l
                 in resources[0]['c7n:ServiceLimitsExceeded']]),
            set(['us-east-1']))
        self.assertEqual(
            set([l['check'] for l
                 in resources[0]['c7n:ServiceLimitsExceeded']]),
            set(['DB security groups']))
        self.assertEqual(len(resources[0]['c7n:ServiceLimitsExceeded']), 1)

    def test_service_limit_specific_service(self):
        session_factory = self.replay_flight_data('test_account_service_limit')
        p = self.load_policy({
            'name': 'service-limit',
            'resource': 'account',
            'region': 'us-east-1',
            'filters': [{
                'type': 'service-limit', 'services': ['IAM'], 'threshold': 1.0
            }]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            set([l['service'] for l
                 in resources[0]['c7n:ServiceLimitsExceeded']]),
            set(['IAM']))
        self.assertEqual(len(resources[0]['c7n:ServiceLimitsExceeded']), 2)

    def test_service_limit_global_service(self):
        policy = {
            'name': 'service-limit',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit', 'services': ['IAM']
            }]}
        self.assertRaises(FilterValidationError, self.load_policy, policy)

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

    def test_account_virtual_mfa(self):
        # only warns when the default threshold goes to warning or above
        session_factory = self.replay_flight_data('test_account_virtual_mfa')
        p1 = self.load_policy({
            'name': 'account-virtual-mfa',
            'resource': 'account',
            'filters': [{
                'type': 'has-virtual-mfa'}]},
            session_factory=session_factory)
        resources = p1.run()
        self.assertEqual(len(resources), 1)

        p2 = self.load_policy({
            'name': 'account-virtual-mfa',
            'resource': 'account',
            'filters': [{
                'type': 'has-virtual-mfa',
                'value': True}]},
            session_factory=session_factory)
        resources = p2.run()
        self.assertEqual(len(resources), 1)

        p3 = self.load_policy({
            'name': 'account-virtual-mfa',
            'resource': 'account',
            'filters': [{
                'type': 'has-virtual-mfa',
                'value': False}]},
            session_factory=session_factory)
        resources = p3.run()
        self.assertEqual(len(resources), 0)

    def test_missing_password_policy(self):
        session_factory = self.replay_flight_data('test_account_missing_password_policy')
        p = self.load_policy({
            'name': 'missing-password-policy',
            'resource': 'account',
            'filters': [{
                'type': 'password-policy', 'key': 'PasswordPolicyConfigured', 'value': False}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_create_trail(self):
        factory = self.replay_flight_data('test_cloudtrail_create')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'account',
                'actions': [
                    {
                        'type': 'enable-cloudtrail',
                        'trail': TRAIL,
                        'bucket': '%s-bucket' % TRAIL,
                    },
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp['trailList']
        arn = trails[0]['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])

    def test_create_trail_bucket_exists_in_west(self):
        config = Config.empty(account_id='644160558196', region='us-west-1')
        factory = self.replay_flight_data('test_cloudtrail_create_bucket_exists_in_west')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'account',
                'region': 'us-west-1',
                'actions': [
                    {
                        'type': 'enable-cloudtrail',
                        'trail': TRAIL,
                        'bucket': '%s-bucket' % TRAIL,
                        'bucket-region': 'us-west-1'
                    },
                ],
            },
            session_factory=factory,
            config=config
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp['trailList']
        arn = trails[0]['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])

    def test_raise_service_limit(self):
        magic_string = 'Programmatic test'

        session_factory = self.replay_flight_data('test_account_raise_service_limit')
        p = self.load_policy({
            'name': 'raise-service-limit-policy',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'services': ['EBS'],
                'threshold': 0.01,
            }],
            'actions': [{
                'type': 'request-limit-increase',
                'percent-increase': 50,
                'subject': magic_string,
            }]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client('support')
        cases = support.describe_cases()
        found = False
        for case in cases['cases']:
            if case['subject'] == magic_string:
                found = True
                break
        self.assertTrue(found)

    def test_raise_service_limit_percent(self):
        magic_string = 'Programmatic test--PLEASE IGNORE {account} {service} in {region}'

        session_factory = self.replay_flight_data('test_account_raise_service_limit_percent')
        p = self.load_policy({
            'name': 'raise-service-limit-policy',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'services': ['VPC', 'RDS'],
                'limits': ['VPCs', 'DB parameter groups'],
                'threshold': 0,
            }],
            'actions': [{
                'type': 'request-limit-increase',
                'percent-increase': 10,
                'subject': magic_string,
            }]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client('support')
        cases = support.describe_cases()
        found = []
        for case in cases['cases']:
            if case['subject'].startswith('Programmatic test--PLEASE IGNORE'):
                self.assertTrue('VPC' in case['subject'] or 'RDS' in case['subject'] and '644160558196' in case['subject'])
                found.append(case)

        self.assertEqual(len(found), 2)
        self.assertTrue(found)

    def test_raise_service_limit_amount(self):
        magic_string = 'Programmatic test--PLEASE IGNORE'

        session_factory = self.replay_flight_data('test_account_raise_service_limit_percent')
        p = self.load_policy({
            'name': 'raise-service-limit-policy',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'services': ['VPC', 'RDS'],
                'limits': ['VPCs', 'DB parameter groups'],
                'threshold': 0,
            }],
            'actions': [{
                'type': 'request-limit-increase',
                'amount-increase': 10,
                'subject': magic_string ,
            }]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client('support')
        cases = support.describe_cases()
        found = []
        for case in cases['cases']:
            if case['subject'].startswith('Programmatic test--PLEASE IGNORE'):
                self.assertTrue('VPC' in case['subject'] or 'RDS' in case['subject'])
                self.assertTrue('644160558196' in case['subject'])
                found.append(case)

        self.assertEqual(len(found), 2)
        self.assertTrue(found)

    def test_raise_service_limit_percent_and_amount(self):
        policy = {
            'name': 'raise-service-limit-policy',
            'resource': 'account',
            'filters': [{
                'type': 'service-limit',
                'services': ['VPC', 'IAM'],
                'limits': ['VPCs', 'Roles'],
                'threshold': 0.01,
            }],
            'actions': [{
                'type': 'request-limit-increase',
                'amount-increase': 10,
                'percent-increase': 10,
            }]},
        self.assertRaises(ValidationError, self.load_policy, policy, validate=True)


    def test_enable_trail(self):
        factory = self.replay_flight_data('test_cloudtrail_enable')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'account',
                'actions': [
                    {
                        'type': 'enable-cloudtrail',
                        'trail': TRAIL,
                        'bucket': '%s-bucket' % TRAIL,
                        'multi-region': False,
                        'global-events': False,
                        'notify': 'test',
                        'file-digest': True,
                        'kms': True,
                        'kms-key': 'arn:aws:kms:us-east-1:1234:key/fake',
                    },
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp['trailList']
        test_trail = trails[0]
        self.assertFalse(test_trail['IsMultiRegionTrail'])
        self.assertFalse(test_trail['IncludeGlobalServiceEvents'])
        self.assertTrue(test_trail['LogFileValidationEnabled'])
        self.assertEqual(test_trail['SnsTopicName'], 'test')
        arn = test_trail['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])


class AccountDataEvents(BaseTest):

    def test_modify_data_events(self):
        session_factory = self.replay_flight_data(
            'test_account_modify_data_events')
        p = self.load_policy({
            'name': 's3-data-events',
            'resource': 'account',
            'actions': [
                {'type': 'enable-data-events',
                 'data-trail': {
                     'create': True,
                     'name': 'S3-DataEvent-1',
                     's3-bucket': 'custodian-skunk-trails',
                     's3-prefix': 'DataEvents',
                     'multi-region': 'us-east-1'}}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n_data_trail']['Name'], 'S3-DataEvent-1')
        client = session_factory().client('cloudtrail')
        self.assertEqual(
            client.get_event_selectors(
                TrailName='S3-DataEvent-1').get('EventSelectors')[-1],
            {'DataResources': [{'Type': 'AWS::S3::Object',
                                'Values': ['arn:aws:s3:::']}],
             'IncludeManagementEvents': False,
             'ReadWriteType': 'All'})

    @functional
    def test_data_events(self):
        session_factory = self.replay_flight_data('test_account_data_events')
        client = session_factory().client('cloudtrail')
        self.assertFalse(
            'S3-DataEvents' in {t['Name'] for t in
                                client.describe_trails().get('trailList')})
        self.addCleanup(client.delete_trail, Name='S3-DataEvents')

        p = self.load_policy({
            'name': 's3-data-events',
            'resource': 'account',
            'actions': [
                {'type': 'enable-data-events',
                 'data-trail': {
                     'create': True,
                     'name': 'S3-DataEvents',
                     's3-bucket': 'custodian-skunk-trails',
                     's3-prefix': 'DataEvents',
                     'multi-region': 'us-east-1'}}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(
            client.get_event_selectors(
                TrailName='S3-DataEvents').get('EventSelectors')[0],
            {'DataResources': [{'Type': 'AWS::S3::Object',
                                'Values': ['arn:aws:s3:::']}],
             'IncludeManagementEvents': False,
             'ReadWriteType': 'All'})

        # Check s3 filter for data events reports them correctly
        from c7n.resources import s3
        self.patch(s3.S3, 'executor_factory', MainThreadExecutor)
        self.patch(s3, 'S3_AUGMENT_TABLE', [])
        p = self.load_policy({
            'name': 's3-data-check',
            'resource': 's3',
            'filters': [
                {'Name': 'custodian-skunk-trails'},
                {'type': 'data-events',
                 'state': 'present'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
