# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.provider import clouds
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.utils import local_session, format_string_values
from c7n.resources import account
from c7n.testing import mock_datetime_now

from pytest_terraform import terraform

import datetime
from dateutil import parser, tz
import json
import logging
import time
from unittest import mock

from .common import functional

TRAIL = "nosetest"


class AccountTests(BaseTest):

    def test_macie(self):
        factory = self.replay_flight_data(
            'test_account_check_macie')
        p = self.load_policy({
            'name': 'macie-check',
            'resource': 'aws.account',
            'filters': [{
                'or': [
                    {'type': 'check-macie',
                     'value': 'absent',
                     'key': 'administrator.accountId'},
                    {'type': 'check-macie',
                     'key': 'status',
                     'value': 'ENABLED'}]}]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['c7n:macie'] == {
            'createdAt': datetime.datetime(
                2020, 12, 3, 16, 22, 14, 821000, tzinfo=tz.tzutc()),
            'findingPublishingFrequency': 'FIFTEEN_MINUTES',
            'administrator': {},
            'master': {},
            'serviceRole': ('arn:aws:iam::{}:role/aws-service-role/'
                            'macie.amazonaws.com/'
                            'AWSServiceRoleForAmazonMacie').format(
                                p.options.account_id),
            'status': 'ENABLED',
            'updatedAt': datetime.datetime(
                2020, 12, 3, 16, 22, 14, 821000, tzinfo=tz.tzutc()),
        }

    def test_macie_disabled(self):
        factory = self.replay_flight_data(
            'test_account_check_macie_disabled')
        p = self.load_policy({
            'name': 'macie-check-disabled',
            'resource': 'aws.account',
            'filters': [{
                'not': [
                    {'type': 'check-macie',
                     'key': 'status',
                     'value': 'ENABLED'}]}]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_org_no_org(self):
        factory = self.replay_flight_data(
            'test_account_org_no_org')
        p = self.load_policy({
            'name': 'org-check',
            'resource': 'aws.account',
            'filters': [{
                'type': 'organization',
                'key': 'Id',
                'value': 'absent'
            }]},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_org_denied(self):
        factory = self.replay_flight_data(
            'test_account_org_info_denied')
        p = self.load_policy({
            'name': 'org-check',
            'resource': 'aws.account',
            'filters': [{
                'type': 'organization',
                'key': 'Id',
                'value': 'absent'
            }]},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_org_info(self):
        factory = self.replay_flight_data(
            'test_account_org_info')
        p = self.load_policy({
            'name': 'org-check',
            'resource': 'aws.account',
            'filters': [{
                'type': 'organization',
                'key': 'Id',
                'op': 'not-equal',
                'value': 'o-xyz'
            }]},
            session_factory=factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:org']['FeatureSet'], 'ALL')

    def test_missing(self):
        session_factory = self.replay_flight_data(
            'test_account_missing_resource_ec2')
        p = self.load_policy({
            'name': 'missing-resource',
            'resource': 'aws.account',
            'filters': [{
                'type': 'missing',
                'policy': {
                    'resource': 'aws.ec2'}
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(sorted(list(resources[0].keys())),
                         sorted(['account_id', 'account_name']))

    def test_missing_multi_region(self):
        # missing filter needs some special handling as it embeds
        # a resource policy inside an account. We treat the account
        # as a global resource, while the resources are typically regional
        # specific. By default missing fires if any region executed against
        # is missing the regional resource.
        cfg = dict(regions=["eu-west-1", "us-west-2"])

        session_factory = self.replay_flight_data('test_account_missing_region_resource')

        class SessionFactory:

            def __init__(self, options):
                self.region = options.region

            def __call__(self, region=None, assume=None):
                return session_factory(region=self.region)

        self.patch(clouds['aws'], 'get_session_factory',
                   lambda x, *args: SessionFactory(*args))

        p = self.load_policy({
            'name': 'missing-lambda',
            'resource': 'aws.account',
            'filters': [{
                'type': 'missing',
                'policy': {
                    'resource': 'aws.lambda'}
            }]},
            session_factory=session_factory, config=cfg)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_enable_encryption_by_default(self):
        factory = self.replay_flight_data('test_account_ebs_encrypt')
        p = self.load_policy({
            'name': 'account',
            'resource': 'account',
            'filters': [{
                'type': 'default-ebs-encryption',
                'state': False}],
            'actions': [{
                'type': 'set-ebs-encryption',
                'state': True,
                'key': 'alias/aws/ebs'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('ec2')
        self.assertTrue(
            client.get_ebs_encryption_by_default().get(
                'EbsEncryptionByDefault'))

    def test_disable_encryption_by_default(self):
        factory = self.replay_flight_data('test_account_disable_ebs_encrypt')
        p = self.load_policy({
            'name': 'account',
            'resource': 'account',
            'filters': [{
                'type': 'default-ebs-encryption',
                'key': 'alias/aws/ebs',
                'state': True}],
            'actions': [{
                'type': 'set-ebs-encryption',
                'state': False}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('ec2')
        self.assertFalse(
            client.get_ebs_encryption_by_default().get(
                'EbsEncryptionByDefault'))

    def test_guard_duty_filter(self):
        factory = self.replay_flight_data('test_account_guard_duty_filter')
        p = self.load_policy({
            'name': 'account',
            'resource': 'account',
            'filters': [{
                'type': 'guard-duty',
                'Detector.Status': 'ENABLED'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:guard-duty' in resources[0])

    def test_root_mfa_enabled(self):
        session_factory = self.replay_flight_data("test_account_root_mfa")
        p = self.load_policy(
            {
                "name": "root-mfa",
                "resource": "account",
                "filters": [
                    {"type": "iam-summary", "key": "AccountMFAEnabled", "value": False}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_root_api_keys(self):
        session_factory = self.replay_flight_data("test_account_root_api_keys")
        p = self.load_policy(
            {
                "name": "root-api",
                "resource": "account",
                "filters": [{"type": "iam-summary"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_s3_public_block_filter_missing(self):
        session_factory = self.replay_flight_data('test_account_filter_s3_public_block_missing')
        p = self.load_policy({
            'name': 'account-s3-public-block',
            'resource': 'account',
            'filters': [{
                'type': 's3-public-block',
                'key': 'BlockPublicPolicy',
                'value': 'empty'}]},
            config={'account_id': '644160558196'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:s3-public-block'], {})

    def test_s3_set_public_block_action(self):
        session_factory = self.replay_flight_data('test_account_action_s3_public_block')
        p = self.load_policy({
            'name': 'account-s3-public-block',
            'resource': 'account',
            'filters': [{
                'type': 's3-public-block',
                'key': 'BlockPublicPolicy',
                'value': False}],
            'actions': [{
                'type': 'set-s3-public-block',
                'BlockPublicPolicy': True}]},
            config={'account_id': '644160558196'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(2)

        client = session_factory().client('s3control')
        block = client.get_public_access_block(
            AccountId='644160558196')['PublicAccessBlockConfiguration']
        self.assertEqual(
            block,
            {'BlockPublicAcls': True,
             'BlockPublicPolicy': True,
             'IgnorePublicAcls': False,
             'RestrictPublicBuckets': False})

    def test_ami_block_public_access_enabled(self):
        factory = self.replay_flight_data('test_ami_block_public_access_enabled')
        p = self.load_policy({
            'name': 'ami-check-block-enabled',
            'resource': 'aws.account',
            'filters': [{
                'type': 'ami-block-public-access',
                'value': True
            }]},
            session_factory=factory)
        resources = p.run()
        # Should return the active account when blocking is enabled
        self.assertEqual(len(resources), 1)

    def test_ami_block_public_access_disabled(self):
        factory = self.replay_flight_data('test_ami_block_public_access_disabled')
        p = self.load_policy({
            'name': 'ami-check-block-disabled',
            'resource': 'aws.account',
            'filters': [{
                'type': 'ami-block-public-access',
                'value': False
            }]},
            session_factory=factory)
        resources = p.run()
        # Should return the active account when blocking is disabled
        self.assertEqual(len(resources), 1)

    def test_ami_block_public_access_mismatch(self):
        factory = self.replay_flight_data('test_ami_block_public_access_enabled')
        p = self.load_policy({
            'name': 'ami-check-block-mismatch',
            'resource': 'aws.account',
            'filters': [{
                'type': 'ami-block-public-access',
                'value': False  # Looking for disabled, but account has it enabled
            }]},
            session_factory=factory)
        resources = p.run()
        # Shouldn't match when account state doesn't match filter
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_enabled(self):
        session_factory = self.replay_flight_data("test_account_trail")
        p = self.load_policy(
            {
                "name": "trail-enabled",
                "resource": "account",
                "filters": [
                    {
                        "type": "check-cloudtrail",
                        "multi-region": True,
                        "kms": True,
                        "file-digest": True,
                        "global-events": True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_current_region_global(self):
        session_factory = self.replay_flight_data("test_account_trail")
        p = self.load_policy(
            {
                "name": "trail-global",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "current-region": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_current_region_specific_same(self):
        session_factory = self.replay_flight_data("test_account_trail_same_region")
        p = self.load_policy(
            {
                "name": "trail-same-region",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "current-region": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_current_region_specific_different(self):
        session_factory = self.replay_flight_data("test_account_trail_different_region")
        p = self.load_policy(
            {
                "name": "trail-different-region",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "current-region": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_cloudtrail_running(self):
        session_factory = self.replay_flight_data("test_cloudtrail_enable")
        p = self.load_policy(
            {
                "name": "trail-running",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "running": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_notifies_disabled(self):
        session_factory = self.replay_flight_data("test_account_trail")
        p = self.load_policy(
            {
                "name": "trail-notifies-disabled",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "notifies": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_cloudtrail_notifies_enabled(self):
        session_factory = self.replay_flight_data("test_cloudtrail_enable")
        p = self.load_policy(
            {
                "name": "trail-notifies-disabled",
                "resource": "account",
                "filters": [{"type": "check-cloudtrail", "notifies": True}],
            },
            session_factory=session_factory,
        )
        # Skip first DescribeTrail/GetTrailStatus call
        client = local_session(session_factory).client("cloudtrail")
        t = client.describe_trails()["trailList"][0]
        client.get_trail_status(Name=t["TrailARN"])
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_success_regex_log_metric_filter(self):
        session_factory = self.replay_flight_data("test_cloudtrail_success_regex_log_metric_filter")
        pdata = {
            'name': 'success-regex-log-metric-filter',
            'resource': 'account',
            'filters': [
                {
                    'type': 'check-cloudtrail',
                    'log-metric-filter-pattern':
                        {
                            'type': 'value',
                            'op': 'regex',
                            'value': '\\{ ?(\\()? ?\\$\\.eventName ?= ?(")?ConsoleLogin(")? '
                                     '?(\\))? ?&& ?(\\()? ?\\$\\.errorMessage ?= '
                                     '?(")?Failed authentication(")? ?(\\))? ?\\}'
                        }
                },
            ],
            }
        p = self.load_policy(
            pdata,
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)
        logs_client = local_session(session_factory).client("logs")
        logs_metrics = logs_client.describe_metric_filters(logGroupName='test_log_group')
        self.assertRegex(logs_metrics['metricFilters'][0]['filterPattern'],
                         pdata['filters'][0]['log-metric-filter-pattern']['value'])

    def test_cloudtrail_fail_regex_log_metric_filter(self):
        session_factory = self.replay_flight_data("test_cloudtrail_fail_regex_log_metric_filter")
        pdata = {
            'name': 'success-regex-log-metric-filter',
            'resource': 'account',
            'filters': [
                {
                    'type': 'check-cloudtrail',
                    'log-metric-filter-pattern':
                        '\\{ ?(\\()? ?\\$\\.eventName ?= ?(")?ConsoleLogin(")? ?(\\))? ?&& ?'
                        '(\\()? ?\\$\\.errorMessage ?= ?(")?Failed authentication(")? ?(\\))? ?\\}'
                },
            ],
            }
        p = self.load_policy(
            pdata,
            session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        logs_client = local_session(session_factory).client("logs")
        logs_metrics = logs_client.describe_metric_filters(logGroupName='test_log_group')
        self.assertNotRegex(logs_metrics['metricFilters'][0]['filterPattern'],
                            pdata['filters'][0]['log-metric-filter-pattern'])

    def test_cloudtrail_success_management_advanced_events_included(self):
        session_factory = self.replay_flight_data(
            "test_cloudtrail_success_management_advanced_events_included")
        p = self.load_policy(
            {
                "name": "trail-management-advanced-events-included",
                "resource": "account",
                "filters": [{
                    "type": "check-cloudtrail",
                    'include-management-events': True
                }],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cloudtrail_fail_management_advanced_events_included(self):
        session_factory = self.replay_flight_data(
            "test_cloudtrail_fail_management_advanced_events_included"
        )
        p = self.load_policy(
            {
                "name": "trail-management-advanced-events-included",
                "resource": "account",
                "filters": [{
                    "type": "check-cloudtrail",
                    'include-management-events': True
                }],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_config_enabled(self):
        session_factory = self.replay_flight_data("test_account_config")
        p = self.load_policy(
            {
                "name": "config-enabled",
                "resource": "account",
                "filters": [
                    {"type": "check-config", "all-resources": True, "running": True}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_config_enabled_global(self):
        session_factory = self.replay_flight_data("test_account_config_global")
        p = self.load_policy(
            {
                "name": "config-enabled",
                "resource": "account",
                "filters": [{"type": "check-config", "global-resources": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_credential_report(self):
        session_factory = self.replay_flight_data("test_account_credential_report")
        p = self.load_policy(
            {
                "name": "credential-details",
                "resource": "account",
                "filters": [{"type": "credential", "key": "mfa_active", "value": True}],
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_service_limit_poll_status(self):

        client = mock.MagicMock()
        client.describe_trusted_advisor_check_result.side_effect = [
            {'result': {'status': 'not_available'}},
            {'result': True}]
        client.describe_trusted_advisor_check_refresh_statuses.return_value = {
            'statuses': [{'status': 'success'}]}

        def time_sleep(interval):
            return

        self.patch(account.time, 'sleep', time_sleep)
        self.assertEqual(
            account.ServiceLimit.get_check_result(client, 'bogusid'),
            True)

    def test_service_limit_specific_check(self):
        session_factory = self.replay_flight_data("test_account_service_limit")
        p = self.load_policy(
            {
                "name": "service-limit",
                "resource": "account",
                "filters": [
                    {
                        "type": "service-limit",
                        "names": ["RDS DB Instances"],
                        "threshold": 1.0,
                    }
                ],
            },
            session_factory=session_factory,
        )
        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {l["service"] for l in resources[0]["c7n:ServiceLimitsExceeded"]},
            {"RDS"},
        )
        self.assertEqual(
            {l["region"] for l in resources[0]["c7n:ServiceLimitsExceeded"]},
            {"us-east-1"},
        )
        self.assertEqual(
            {l["check"] for l in resources[0]["c7n:ServiceLimitsExceeded"]},
            {"DB instances"},
        )
        self.assertEqual(len(resources[0]["c7n:ServiceLimitsExceeded"]), 1)

    def test_service_limit_specific_check_handles_exception(self):
        session_factory = self.replay_flight_data("test_account_service_limit_exception")
        p = self.load_policy(
            {
                "name": "service-limit",
                "resource": "account",
                "filters": [
                    {
                        "type": "service-limit",
                        "names": ["RDS DB Instances"],
                        "threshold": 1.0,
                    }
                ],
            },
            session_factory=session_factory,
        )
        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime) and \
         self.capture_logging(level=logging.WARNING) as log_output:
            resources = p.run()
            self.assertEqual(0, len(resources))
            self.assertRegex(log_output.getvalue(), r"InvalidParameterValueException")

    def test_service_limit_specific_check_handles_exception_on_date_refresh(self):
        session_factory = self.replay_flight_data(
            "test_account_service_limit_date_refresh_exception")
        p = self.load_policy(
            {
                "name": "service-limit",
                "resource": "account",
                "filters": [
                    {
                        "type": "service-limit",
                        "names": ["RDS DB Instances"],
                        "threshold": 1.0,
                    }
                ],
            },
            session_factory=session_factory,
        )
        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime) and \
         self.capture_logging(level=logging.WARNING) as log_output:
            resources = p.run()
            self.assertEqual(0, len(resources))
            self.assertRegex(log_output.getvalue(), r"InvalidParameterValueException")

    def test_service_limit_specific_service(self):
        session_factory = self.replay_flight_data("test_account_service_limit_specific_service")
        p = self.load_policy(
            {
                "name": "service-limit",
                "resource": "account",
                "region": "us-east-1",
                "filters": [
                    {"type": "service-limit", "services": ["IAM"], "threshold": 0.1}
                ],
            },
            session_factory=session_factory,
        )
        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {l["service"] for l in resources[0]["c7n:ServiceLimitsExceeded"]},
            {"IAM"},
        )
        self.assertEqual(len(resources[0]["c7n:ServiceLimitsExceeded"]), 2)

    def test_service_limit_global_service(self):
        policy = {
            "name": "service-limit",
            "resource": "account",
            "filters": [{"type": "service-limit", "services": ["IAM"]}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)

    def test_service_limit_no_threshold(self):
        # only warns when the default threshold goes to warning or above
        session_factory = self.replay_flight_data("test_account_service_limit")
        p = self.load_policy(
            {
                "name": "service-limit",
                "resource": "account",
                "filters": [{"type": "service-limit"}],
            },
            session_factory=session_factory,
        )
        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_account_virtual_mfa(self):
        # only warns when the default threshold goes to warning or above
        session_factory = self.replay_flight_data("test_account_virtual_mfa")
        p1 = self.load_policy(
            {
                "name": "account-virtual-mfa",
                "resource": "account",
                "filters": [{"type": "has-virtual-mfa"}],
            },
            session_factory=session_factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 1)

        p2 = self.load_policy(
            {
                "name": "account-virtual-mfa",
                "resource": "account",
                "filters": [{"type": "has-virtual-mfa", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p2.run()
        self.assertEqual(len(resources), 1)

        p3 = self.load_policy(
            {
                "name": "account-virtual-mfa",
                "resource": "account",
                "filters": [{"type": "has-virtual-mfa", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p3.run()
        self.assertEqual(len(resources), 0)

    def test_missing_password_policy(self):
        session_factory = self.replay_flight_data(
            "test_account_missing_password_policy"
        )
        p = self.load_policy(
            {
                "name": "missing-password-policy",
                "resource": "account",
                "filters": [
                    {
                        "type": "password-policy",
                        "key": "PasswordPolicyConfigured",
                        "value": False,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        assert resources[0]['c7n:password_policy']['PasswordPolicyConfigured'] is False

    def test_account_password_policy_update(self):
        factory = self.replay_flight_data("test_account_password_policy_update")
        p = self.load_policy(
            {
                "name": "set-password-policy",
                "resource": "account",
                "filters": [
                    {
                        "or": [
                            {
                                "not": [
                                    {
                                        "type": "password-policy",
                                        "key": "MinimumPasswordLength",
                                        "value": 12,
                                        "op": "ge"
                                    },
                                    {
                                        "type": "password-policy",
                                        "key": "RequireSymbols",
                                        "value": True
                                    },
                                    {
                                        "type": "password-policy",
                                        "key": "RequireNumbers",
                                        "value": True
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "actions": [
                    {
                        "type": "set-password-policy",
                        "policy": {
                            "MinimumPasswordLength": 12,
                            "RequireSymbols": True,
                            "RequireNumbers": True
                        }
                    }
                ]
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('iam')
        policy = client.get_account_password_policy().get('PasswordPolicy')
        self.assertEqual(
            [
                policy['MinimumPasswordLength'],
                policy['RequireSymbols'],
                policy['RequireNumbers'],
            ],
            [
                12,
                True,
                True,
            ]
        )

    def test_account_password_policy_update_first_time(self):
        factory = self.replay_flight_data("test_account_password_policy_update_first_time")
        p = self.load_policy(
            {
                "name": "set-password-policy",
                "resource": "account",
                "filters": [
                    {
                        "type": "password-policy",
                        "key": "PasswordPolicyConfigured",
                        "value": False,
                    }
                ],
                "actions": [
                    {
                        "type": "set-password-policy",
                        "policy": {
                            "MinimumPasswordLength": 12
                        }
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('iam')
        policy = client.get_account_password_policy().get('PasswordPolicy')
        assert policy['MinimumPasswordLength'] == 12
        # assert defaults being set
        self.assertEqual(
            [
                policy['RequireSymbols'],
                policy['RequireNumbers'],
                policy['RequireUppercaseCharacters'],
                policy['RequireLowercaseCharacters'],
                policy['AllowUsersToChangePassword']
            ],
            [
                False,
                False,
                False,
                False,
                False,
            ]
        )

    def test_create_trail(self):
        factory = self.replay_flight_data("test_cloudtrail_create")
        p = self.load_policy(
            {
                "name": "trail-test",
                "resource": "account",
                "actions": [
                    {
                        "type": "enable-cloudtrail",
                        "trail": TRAIL,
                        "bucket": "%s-bucket" % TRAIL,
                    }
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client("cloudtrail")
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp["trailList"]
        arn = trails[0]["TrailARN"]
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status["IsLogging"])

    def test_create_trail_bucket_exists_in_west(self):
        config = dict(region="us-west-1")
        factory = self.replay_flight_data(
            "test_cloudtrail_create_bucket_exists_in_west"
        )
        p = self.load_policy(
            {
                "name": "trail-test",
                "resource": "account",
                "region": "us-west-1",
                "actions": [
                    {
                        "type": "enable-cloudtrail",
                        "trail": TRAIL,
                        "bucket": "%s-bucket" % TRAIL,
                        "bucket-region": "us-west-1",
                    }
                ],
            },
            session_factory=factory,
            config=config,
        )
        p.run()
        client = local_session(factory).client("cloudtrail")
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp["trailList"]
        arn = trails[0]["TrailARN"]
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status["IsLogging"])

    def test_raise_service_limit(self):
        magic_string = "Programmatic test"

        session_factory = self.replay_flight_data("test_account_raise_service_limit")
        p = self.load_policy(
            {
                "name": "raise-service-limit-policy",
                "resource": "account",
                "filters": [
                    {"type": "service-limit", "services": ["EBS"], "threshold": 0.01}
                ],
                "actions": [
                    {
                        "type": "request-limit-increase",
                        "percent-increase": 50,
                        "subject": magic_string,
                    }
                ],
            },
            session_factory=session_factory,
        )

        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client("support")
        cases = support.describe_cases()
        found = False
        for case in cases["cases"]:
            if case["subject"] == magic_string:
                found = True
                break
        self.assertTrue(found)

    def test_raise_service_limit_percent(self):
        magic_string = "Programmatic test--PLEASE IGNORE {account} {service} in {region}"

        session_factory = self.replay_flight_data(
            "test_account_raise_service_limit_percent"
        )
        p = self.load_policy(
            {
                "name": "raise-service-limit-policy",
                "resource": "account",
                "filters": [
                    {
                        "type": "service-limit",
                        "services": ["VPC", "RDS"],
                        "limits": ["VPCs", "DB parameter groups"],
                        "threshold": 0,
                    }
                ],
                "actions": [
                    {
                        "type": "request-limit-increase",
                        "percent-increase": 10,
                        "subject": magic_string,
                    }
                ],
            },
            session_factory=session_factory,
        )

        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client("support")
        cases = support.describe_cases()
        found = []
        for case in cases["cases"]:
            if case["subject"].startswith("Programmatic test--PLEASE IGNORE"):
                self.assertTrue(
                    "VPC" in case["subject"] or
                    "RDS" in case["subject"] and
                    "644160558196" in case["subject"]
                )
                found.append(case)

        self.assertEqual(len(found), 2)
        self.assertTrue(found)

    def test_raise_service_limit_amount(self):
        magic_string = "Programmatic test--PLEASE IGNORE"

        session_factory = self.replay_flight_data(
            "test_account_raise_service_limit_percent"
        )
        p = self.load_policy(
            {
                "name": "raise-service-limit-policy",
                "resource": "account",
                "filters": [
                    {
                        "type": "service-limit",
                        "services": ["VPC", "RDS"],
                        "limits": ["VPCs", "DB parameter groups"],
                        "threshold": 0,
                    }
                ],
                "actions": [
                    {
                        "type": "request-limit-increase",
                        "amount-increase": 10,
                        "subject": magic_string,
                    }
                ],
            },
            session_factory=session_factory,
        )

        # use this to prevent attempts at refreshing check
        with mock_datetime_now(parser.parse("2017-02-23T00:40:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

        # Validate that a case was created
        support = session_factory().client("support")
        cases = support.describe_cases()
        found = []
        for case in cases["cases"]:
            if case["subject"].startswith("Programmatic test--PLEASE IGNORE"):
                self.assertTrue("VPC" in case["subject"] or "RDS" in case["subject"])
                self.assertTrue("644160558196" in case["subject"])
                found.append(case)

        self.assertEqual(len(found), 2)
        self.assertTrue(found)

    def test_raise_service_limit_percent_and_amount(self):
        policy = {
            "name": "raise-service-limit-policy",
            "resource": "account",
            "filters": [
                {
                    "type": "service-limit",
                    "services": ["VPC", "IAM"],
                    "limits": ["VPCs", "Roles"],
                    "threshold": 0.01,
                }
            ],
            "actions": [
                {
                    "type": "request-limit-increase",
                    "amount-increase": 10,
                    "percent-increase": 10,
                }
            ],
        }
        self.assertRaises(
            PolicyValidationError, self.load_policy, policy, validate=True)

    def test_enable_trail(self):
        factory = self.replay_flight_data("test_cloudtrail_enable")
        p = self.load_policy(
            {
                "name": "trail-test",
                "resource": "account",
                "actions": [
                    {
                        "type": "enable-cloudtrail",
                        "trail": TRAIL,
                        "bucket": "%s-bucket" % TRAIL,
                        "multi-region": False,
                        "global-events": False,
                        "notify": "test",
                        "file-digest": True,
                        "kms": True,
                        "kms-key": "arn:aws:kms:us-east-1:1234:key/fake",
                    }
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client("cloudtrail")
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp["trailList"]
        test_trail = trails[0]
        self.assertFalse(test_trail["IsMultiRegionTrail"])
        self.assertFalse(test_trail["IncludeGlobalServiceEvents"])
        self.assertTrue(test_trail["LogFileValidationEnabled"])
        self.assertEqual(test_trail["SnsTopicName"], "test")
        arn = test_trail["TrailARN"]
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status["IsLogging"])

    def test_account_access_analyzer_filter(self):
        session_factory = self.replay_flight_data("test_account_access_analyzer_filter")
        p = self.load_policy(
            {
                "name": "account-access-analyzer",
                "resource": "account",
                "filters": [{"type": "access-analyzer",
                             "key": "status",
                             "value": "ACTIVE",
                             "op": "eq"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_account_shield_filter(self):
        session_factory = self.replay_flight_data("test_account_shield_advanced_filter")
        p = self.load_policy(
            {
                "name": "account-shield",
                "resource": "account",
                "filters": ["shield-enabled"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_account_shield_activate(self):
        session_factory = self.replay_flight_data("test_account_shield_advanced_enable")
        p = self.load_policy(
            {
                "name": "account-shield",
                "resource": "account",
                "filters": ["shield-enabled"],
                "actions": ["set-shield-advanced"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        p = self.load_policy(
            {
                "name": "account-shield",
                "resource": "account",
                "filters": [{"type": "shield-enabled", "state": True}],
            },
            session_factory=session_factory,
        )
        self.assertEqual(len(p.run()), 1)

    def test_glue_catalog_encrypted_filter(self):
        session_factory = self.replay_flight_data("test_account_glue_encyption_filter")
        p = self.load_policy(
            {
                "name": "glue-security-config",
                "resource": "account",
                'filters': [{
                    'type': 'glue-security-config',
                    'CatalogEncryptionMode': 'SSE-KMS'},
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_glue_password_encryption_setting(self):
        session_factory = self.replay_flight_data("test_account_glue_encyption_filter")
        p = self.load_policy(
            {
                "name": "glue-security-config",
                "resource": "account",
                'filters': [{
                    'type': 'glue-security-config',
                    'SseAwsKmsKeyId': 'alias/aws/glue'},
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_glue_connection_password_encryption(self):
        session_factory = self.replay_flight_data("test_account_glue_connection_password_filter")
        p = self.load_policy(
            {
                "name": "glue-security-config",
                "resource": "account",
                'filters': [{
                    'type': 'glue-security-config',
                    'AwsKmsKeyId': 'alias/skunk/trails'},
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_get_emr_block_public_access_configuration(self):
        session_factory = self.replay_flight_data("test_emr_block_public_access_configuration")
        p = self.load_policy(
            {
                'name': 'get-emr-block-public-access-configuration',
                'resource': 'account',
                'filters': [{
                    'type': 'emr-block-public-access',
                    'key': 'BlockPublicAccessConfiguration',
                    'value': 'not-null'
                }]
            },
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:emr-block-public-access"]
            ['BlockPublicAccessConfigurationMetadata']['CreatedByArn'],
            "arn:aws:iam::12345678901:user/test")

    def test_set_emr_block_public_access_configuration(self):
        session_factory = self.replay_flight_data("test_set_emr_block_public_access_configuration")
        p = self.load_policy(
            {
                'name': 'emr',
                'resource': 'account',
                'actions': [{
                    "type": "set-emr-block-public-access",
                    "config": {
                        "BlockPublicSecurityGroupRules": True,
                        "PermittedPublicSecurityGroupRuleRanges": [{
                            "MinRange": 23,
                            "MaxRange": 23,
                        }]
                    }
                }],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(session_factory).client("emr")
        resp = client.get_block_public_access_configuration()

        self.assertEqual(resp["BlockPublicAccessConfiguration"]
            ["PermittedPublicSecurityGroupRuleRanges"][0]['MinRange'], 23)
        self.assertEqual(resp["BlockPublicAccessConfiguration"]
            ["PermittedPublicSecurityGroupRuleRanges"][0]['MaxRange'], 23)

    def test_ses_agg_send_stats(self):
        factory = self.replay_flight_data('test_ses_agg_send_stats')
        p = self.load_policy({
            'name': 'ses-agg-send-stats-policy',
            'resource': 'account',
            'filters': [{"type": "ses-agg-send-stats"}]},
            config={'region': 'us-west-2'},
            session_factory=factory)
        resources = p.run()
        expected_agg_send_stats = {
            'DeliveryAttempts': 130,
            'Bounces': 1,
            'Complaints': 0,
            'Rejects': 0,
            'BounceRate': 1
        }
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:ses-send-agg'], expected_agg_send_stats)

    def test_ses_consecutive_send_stats(self):
        factory = self.replay_flight_data('test_ses_agg_send_stats')
        p = self.load_policy({
            'name': 'ses-consecutive-stats',
            'resource': 'account',
            'filters': [{"type": "ses-send-stats", "days": 2}]},
            config={'region': 'us-west-2'},
            session_factory=factory)
        with mock_datetime_now(parser.parse("2022-10-26T00:00:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        expected_send_stats = [{
            'DeliveryAttempts': 17,
            'Bounces': 1,
            'Complaints': 0,
            'Rejects': 0,
            'BounceRate': 6,
            'Date': '2022-10-25'}, {
            'DeliveryAttempts': 20,
            'Bounces': 0,
            'Complaints': 0,
            'Rejects': 0,
            'BounceRate': 0,
            'Date': '2022-10-24'}
        ]
        self.assertEqual(resources[0]['c7n:ses-send-stats'], expected_send_stats)
        self.assertEqual(resources[0]['c7n:ses-max-bounce-rate'], 6)

    def test_bedrock_model_invocation_logging_disabled(self):
        factory = self.replay_flight_data('test_bedrock_model_invocation_logging_disabled')
        p = self.load_policy({
            'name': 'bedrock-model-invocation-logging-disabled',
            'resource': 'account',
            'filters': [
                            {
                                "type": "bedrock-model-invocation-logging",
                                "count": 0,
                                "count_op": "eq"
                            }
                        ]
                        },
            config={'region': 'us-east-1'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_get_bedrock_model_invocation_logging(self):
        factory = self.replay_flight_data('test_get_bedrock_model_invocation_logging')
        p = self.load_policy({
            'name': 'get-bedrock-model-invocation-logging',
            'resource': 'account',
            'filters': [
                            {
                                "type": "bedrock-model-invocation-logging",
                                "attrs": [
                                    {"s3Config": "not-null"},
                                    {"imageDataDeliveryEnabled": True}
                                ]
                            }
                        ]
                        },
            config={'region': 'us-east-1'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_bedrock_model_invocation_logging(self):
        factory = self.replay_flight_data('test_delete_bedrock_model_invocation_logging')
        p = self.load_policy({
            'name': 'delete-bedrock-model-invocation-logging',
            'resource': 'account',
            'actions': [
                            {
                                "type": "set-bedrock-model-invocation-logging",
                                "enabled": False
                            }
                        ]
                        },
            config={'region': 'us-east-1'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_update_bedrock_model_invocation_logging(self):
        factory = self.replay_flight_data("test_update_bedrock_model_invocation_logging")
        p = self.load_policy(
            {
                "name": "set-bedrock-model-invocation-logging",
                "resource": "account",
                "actions": [
                    {
                        "type": "set-bedrock-model-invocation-logging",
                        "enabled": True,
                        "loggingConfig": {
                            "textDataDeliveryEnabled": True,
                            "imageDataDeliveryEnabled": True,
                            "embeddingDataDeliveryEnabled": False,
                            "s3Config":
                                {
                                    "bucketName": "test-bedrock-1",
                                    "keyPrefix": "logging/"
                                }
                        }
                    }
                ]
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('bedrock')
        configuration = client.get_model_invocation_logging_configuration()
        self.assertEqual(
            [
                configuration['loggingConfig']['textDataDeliveryEnabled'],
                configuration['loggingConfig']['imageDataDeliveryEnabled'],
                configuration['loggingConfig']['embeddingDataDeliveryEnabled'],
                configuration['loggingConfig']['s3Config']['bucketName'],
                configuration['loggingConfig']['s3Config']['keyPrefix']
            ],
            [
                True,
                True,
                False,
                "test-bedrock-1",
                "logging/"
            ]
        )

    def test_ec2_metadata_defaults(self):

        factory = self.replay_flight_data("test_ec2_metadata_defaults")
        p = self.load_policy(
            {
                "name": "ec2-metadata-defaults",
                "resource": "account",
                "filters": [{
                    "type": "ec2-metadata-defaults",
                    "key": "HttpTokens",
                    "value": "optional"
                }],
                "actions": [{
                        "type": "set-ec2-metadata-defaults",
                        "HttpTokens": "required",
                        "HttpPutResponseHopLimit": 1,
                        "HttpEndpoint": "enabled",
                        "InstanceMetadataTags": "enabled"
                }],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(factory).client('ec2')
        defaults = client.get_instance_metadata_defaults()["AccountLevel"]
        self.assertEqual(
            [
                defaults["HttpTokens"],
                defaults["HttpPutResponseHopLimit"],
                defaults["HttpEndpoint"],
                defaults["InstanceMetadataTags"],
            ],
            [
                "required",
                1,
                "enabled",
                "enabled",
            ]
        )

    def test_set_security_token_service_preferences(self):

        factory = self.replay_flight_data("test_set_security_token_service_preferences")
        p = self.load_policy(
            {
                "name": "set-sts-preferences",
                "resource": "account",
                "actions": [
                    {
                        "type": "set-security-token-service-preferences",
                        "token_version": "v2Token",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = local_session(factory).client("iam")
        response = client.get_account_summary()
        # self.assertIn("SummaryMap", response['SummaryMap'])
        self.assertIn("SummaryMap", response)

        # Verify that the token version was set correctly

        self.assertEqual(2, response['SummaryMap']['GlobalEndpointTokenVersion'])


class AccountDataEvents(BaseTest):

    def make_bucket(self, session_factory, name):
        client = session_factory().client("s3")

        buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}
        if name in buckets:
            self.destroyBucket(client, name)

        # It is not accepted to pass us-east-1 to create_bucket
        region = client._client_config.region_name
        if region == "us-east-1":
            client.create_bucket(Bucket=name)
        else:
            config = {"LocationConstraint": client._client_config.region_name}
            client.create_bucket(Bucket=name, CreateBucketConfiguration=config)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AWSCloudTrailAclCheck20150319",
                    "Effect": "Allow",
                    "Principal": {"Service": "cloudtrail.amazonaws.com"},
                    "Action": "s3:GetBucketAcl",
                    "Resource": "arn:aws:s3:::{}".format(name),
                },
                {
                    "Sid": "AWSCloudTrailWrite20150319",
                    "Effect": "Allow",
                    "Principal": {"Service": "cloudtrail.amazonaws.com"},
                    "Action": "s3:PutObject",
                    "Resource": "arn:aws:s3:::{}/*".format(name),
                    "Condition": {
                        "StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}
                    },
                },
            ],
        }

        client.put_bucket_policy(Bucket=name, Policy=json.dumps(policy))
        self.addCleanup(self.destroyBucket, client, name)

    def destroyBucket(self, client, bucket):
        for o in client.list_objects(Bucket=bucket).get("Contents", ()):
            client.delete_object(Bucket=bucket, Key=o["Key"])
        client.delete_bucket(Bucket=bucket)

    def test_modify_data_events(self):
        session_factory = self.replay_flight_data("test_account_modify_data_events")
        client = session_factory().client("cloudtrail")

        region = client._client_config.region_name
        trail_name = "S3-DataEvents-test1"
        bucket_name = "skunk-trails-test-{}".format(region)

        self.make_bucket(session_factory, bucket_name)
        self.addCleanup(client.delete_trail, Name=trail_name)

        p = self.load_policy(
            {
                "name": "s3-data-events",
                "resource": "account",
                "actions": [
                    {
                        "type": "enable-data-events",
                        "data-trail": {
                            "create": True,
                            "name": trail_name,
                            "s3-bucket": bucket_name,
                            "s3-prefix": "DataEvents",
                            "multi-region": region,
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n_data_trail"]["Name"], trail_name)
        self.assertEqual(
            client.get_event_selectors(TrailName=trail_name).get("EventSelectors")[-1],
            {
                "DataResources": [
                    {"Type": "AWS::S3::Object", "Values": ["arn:aws:s3:::"]}
                ],
                "IncludeManagementEvents": False,
                "ReadWriteType": "All",
            },
        )

    @functional
    def test_data_events(self):
        session_factory = self.replay_flight_data("test_account_data_events")
        client = session_factory().client("cloudtrail")

        region = client._client_config.region_name
        trail_name = "S3-DataEvents-test2"
        bucket_name = "skunk-trails-test-{}".format(region)

        self.make_bucket(session_factory, bucket_name)

        existing_trails = {t["Name"] for t in client.describe_trails().get("trailList")}
        if trail_name in existing_trails:
            client.delete_trail(Name=trail_name)

        self.addCleanup(client.delete_trail, Name=trail_name)

        p = self.load_policy(
            {
                "name": "s3-data-events",
                "resource": "account",
                "actions": [
                    {
                        "type": "enable-data-events",
                        "data-trail": {
                            "create": True,
                            "name": trail_name,
                            "s3-bucket": bucket_name,
                            "s3-prefix": "DataEvents",
                            "multi-region": region,
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            client.get_event_selectors(TrailName=trail_name).get("EventSelectors")[0],
            {
                "DataResources": [
                    {"Type": "AWS::S3::Object", "Values": ["arn:aws:s3:::"]}
                ],
                "IncludeManagementEvents": False,
                "ReadWriteType": "All",
            },
        )

        # Check s3 filter for data events reports them correctly
        from c7n.resources import s3

        self.patch(s3.S3, "executor_factory", MainThreadExecutor)
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        p = self.load_policy(
            {
                "name": "s3-data-check",
                "resource": "s3",
                "filters": [
                    {"Name": bucket_name}, {"type": "data-events", "state": "present"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_enable_securityhub(self):
        session_factory = self.replay_flight_data("test_enable_securityhub")
        p = self.load_policy(
            {
                'name': 'enable-sechub',
                'resource': 'account',
                'filters': [{
                    'type': 'securityhub',
                    'enabled': False
                }],
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_lakeformation_filter(self):
        factory = self.replay_flight_data("test_lakeformation_cross_account_s3")
        p = self.load_policy(
            {
                'name': 'test-lakeformation-cross-account-bucket',
                'resource': 'account',
                'filters': [{
                    'type': 'lakeformation-s3-cross-account'
                }],
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.assertEqual(
            resources[0]["c7n:lake-cross-account-s3"], ["testarena.com"])

    def test_toggle_config_managed_rule_validation(self):
        policy = {
            "name": "enable-config-managed-rule-valid",
            "resource": "account",
            "actions": [
                {
                    "type": "toggle-config-managed-rule",
                    "rule_name": "enable-config-managed-rule",
                    "rule_prefix": "test-",
                    "managed_rule_id": "S3_BUCKET_PUBLIC_WRITE_PROHIBITED",
                    "resource_types": [
                        "AWS::S3::Bucket"
                    ],
                }
            ]
        }
        p = self.load_policy(policy)
        p.validate()

        # Make the policy invalid
        del policy["actions"][0]["managed_rule_id"]
        with self.assertRaises(
            PolicyValidationError, msg="managed_rule_id required to enable"
        ):
            p.validate()

    def test_toggle_config_managed_rule(self):
        session_factory = self.replay_flight_data("test_toggle_config_managed_rule")
        policy = {
            "name": "enable-config-managed-rule",
            "resource": "account",
            "actions": [
                {
                    "type": "toggle-config-managed-rule",
                    "rule_name": "enable-config-managed-rule",
                    "rule_prefix": "test-",
                    "managed_rule_id": "S3_BUCKET_PUBLIC_WRITE_PROHIBITED",
                    "resource_types": [
                        "AWS::S3::Bucket"
                    ],
                    "rule_parameters": "{}",
                    "remediation": {
                        "TargetId": "AWS-DisableS3BucketPublicReadWrite",
                        "Automatic": True,
                        "MaximumAutomaticAttempts": 5,
                        "RetryAttemptSeconds": 211,
                        "Parameters": {
                            "AutomationAssumeRole": {
                                "StaticValue": {
                                    "Values": [
                                        "arn:aws:iam::{account_id}:role/myrole"
                                    ]
                                }
                            },
                            "S3BucketName": {
                                "ResourceValue": {
                                    "Value": "RESOURCE_ID"
                                }
                            }
                        }
                    }
                }
            ]
        }

        # Enable the managed rule
        p = self.load_policy(
            policy,
            session_factory=session_factory,
        )
        p.expand_variables(p.get_variables())
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(session_factory).client('config')
        resp = client.describe_config_rules(
            ConfigRuleNames=['test-enable-config-managed-rule']
        )
        self.assertEqual(len(resp['ConfigRules']), 1)
        resp = client.describe_remediation_configurations(
            ConfigRuleNames=['test-enable-config-managed-rule']
        )
        self.assertEqual(len(resp['RemediationConfigurations']), 1)

        # Disable the rule we just enabled
        policy["actions"][0]["enabled"] = False
        p = self.load_policy(
            policy,
            session_factory=session_factory,
        )
        p.expand_variables(p.get_variables())
        resources = p.run()
        self.assertEqual(len(resources), 1)
        resp = client.describe_config_rules(
            ConfigRuleNames=['test-enable-config-managed-rule']
        )
        self.assertEqual(resp['ConfigRules'][0]['ConfigRuleState'], 'DELETING')


@terraform('cloudtrail_success_log_metric_filter')
def test_cloudtrail_success_log_metric_filter(test, cloudtrail_success_log_metric_filter):
    session_factory = test.replay_flight_data('test_cloudtrail_success_log_metric_filter')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'log-metric-filter-pattern':
                    "{{ ($.eventName = ConsoleLogin) && ($.additionalEventData.MFAUsed != Yes) }}"
            },
        ]
    }
    pdata['filters'][0]['log-metric-filter-pattern'] = \
        format_string_values(pdata['filters'][0]['log-metric-filter-pattern'])
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 0)


@terraform('cloudtrail_fail_log_metric_filter_no_alarm')
def test_cloudtrail_fail_log_metric_filter_no_alarm(test,
                                                    cloudtrail_fail_log_metric_filter_no_alarm):
    session_factory = test.replay_flight_data('test_cloudtrail_fail_log_metric_filter_no_alarm')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'log-metric-filter-pattern':
                    "{{ ($.eventName = ConsoleLogin) && ($.additionalEventData.MFAUsed != Yes) }}"
            },
        ]
    }
    pdata['filters'][0]['log-metric-filter-pattern'] = \
        format_string_values(pdata['filters'][0]['log-metric-filter-pattern'])
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 1)


@terraform('cloudtrail_fail_log_metric_filter_no_sns')
def test_cloudtrail_fail_log_metric_filter_no_sns(test, cloudtrail_fail_log_metric_filter_no_sns):
    session_factory = test.replay_flight_data('test_cloudtrail_fail_log_metric_filter_no_sns')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'log-metric-filter-pattern':
                    "{{ ($.eventName = ConsoleLogin) && ($.additionalEventData.MFAUsed != Yes) }}"
            },
        ]
    }
    pdata['filters'][0]['log-metric-filter-pattern'] = \
        format_string_values(pdata['filters'][0]['log-metric-filter-pattern'])
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 1)


@terraform('cloudtrail_fail_log_metric_filter')
def test_cloudtrail_fail_log_metric_filter(test, cloudtrail_fail_log_metric_filter):
    session_factory = test.replay_flight_data('test_cloudtrail_fail_log_metric_filter')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'log-metric-filter-pattern':
                    "{{ ($.eventName = ConsoleLogin) }}"
            },
        ]
    }
    pdata['filters'][0]['log-metric-filter-pattern'] = \
        format_string_values(pdata['filters'][0]['log-metric-filter-pattern'])
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 1)


@terraform('cloudtrail_success_include_management_events')
def test_success_cloudtrail_include_management_events(test,
                                                      cloudtrail_success_include_management_events):
    session_factory = \
        test.replay_flight_data('test_cloudtrail_success_cloudtrail_include_management_events')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'include-management-events': True
            },
        ]
    }
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 0)


@terraform('cloudtrail_fail_include_management_events')
def test_fail_cloudtrail_include_management_events(test, cloudtrail_fail_include_management_events):
    session_factory = test.replay_flight_data('test_cloudtrail_fail_include_management_events')
    pdata = {
        'name': 'check-filter-pattern',
        'resource': 'aws.account',
        'filters': [
            {
                'type': 'check-cloudtrail',
                'include-management-events': True
            },
        ]
    }
    p = test.load_policy(
        pdata,
        session_factory=session_factory
    )
    return_value = p.run()
    test.assertEqual(len(return_value), 1)
