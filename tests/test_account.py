# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.provider import clouds
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.utils import local_session
from c7n.resources import account
from c7n.testing import mock_datetime_now

import datetime
from dateutil import parser, tz
import json
import mock
import time

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
                     'key': 'master.accountId'},
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

        assert(
            resources[0]['c7n:password_policy']['PasswordPolicyConfigured'] is False
        )

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
        assert(
            policy['MinimumPasswordLength'] == 12
        )
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
