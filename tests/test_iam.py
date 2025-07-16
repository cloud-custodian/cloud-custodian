# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
import tempfile
import time
from unittest import mock
from unittest import TestCase

from .common import load_data, BaseTest, functional

import freezegun
import pytest
from pytest_terraform import terraform
from dateutil import parser

from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.filters.iamaccess import CrossAccountAccessFilter, PolicyChecker
from c7n.mu import LambdaManager, LambdaFunction, PythonPackageArchive
from botocore.exceptions import ClientError
from c7n.resources.aws import shape_validate
from c7n.resources.sns import SNS
from c7n.resources.iam import (
    UserMfaDevice,
    UsedIamPolicies,
    UnusedIamPolicies,
    UsedInstanceProfiles,
    UnusedInstanceProfiles,
    UsedIamRole,
    UnusedIamRole,
    IamGroupUsers,
    UserPolicy,
    GroupMembership,
    UserCredentialReport,
    UserAccessKey,
    IamUserInlinePolicy,
    IamRoleInlinePolicy,
    IamGroupInlinePolicy,
    SpecificIamRoleManagedPolicy,
    NoSpecificIamRoleManagedPolicy,
    PolicyQueryParser
)


class UserCredentialReportTest(BaseTest):

    def test_credential_report_generate(self):
        session_factory = self.replay_flight_data("test_iam_user_unused_keys")
        p = self.load_policy(
            {
                "name": "user-access-unused-keys",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.last_used_date",
                        "report_delay": 0.01,
                        "value": "empty",
                    }
                ],
            },
            session_factory=session_factory,
            cache=True,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["UserName"] for r in resources]),
            ["Hazmat", "kapilt"],
        )

    def test_credential_report_generate_in_progress(self):
        session_factory = self.replay_flight_data("test_iam_user_unused_keys_report_in_progress")
        p = self.load_policy(
            {
                "name": "user-access-unused-keys",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.last_used_date",
                        "report_delay": 0.01,
                        "value": "empty",
                    }
                ],
            },
            session_factory=session_factory,
            cache=True,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["UserName"] for r in resources]),
            ["Hazmat", "kapilt"],
        )

    def test_credential_access_key_multifilter_delete(self):
        factory = self.replay_flight_data('test_iam_user_credential_multi_delete')
        p = self.load_policy({
            'name': 'user-cred-multi',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'kapil'},
                {"type": "credential",
                 "report_max_age": 1543724277,
                 "key": "access_keys.last_used_date",
                 "value": 30,
                 'op': 'greater-than',
                 "value_type": "age"},
                {"type": "credential",
                 "report_max_age": 1543724277,
                 "key": "access_keys.last_rotated",
                 "value": 900,
                 "op": "greater-than",
                 'value_type': 'age'}],
            'actions': [
                {'type': 'remove-keys',
                 'matched': True}]},
            session_factory=factory)

        with freezegun.freeze_time('2020-01-01'):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 1)
        client = factory().client('iam')
        if self.recording:
            time.sleep(1)
        keys = client.list_access_keys(UserName='kapil').get('AccessKeyMetadata')
        self.assertEqual(len(keys), 1)
        dt = parser.parse(resources[0]['c7n:matched-keys'][0]['last_rotated'])
        self.assertNotEqual(keys[0]['CreateDate'], dt)
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ["arn:aws:iam::644160558196:user/kapil"])

    def test_credential_access_key_multifilter_delete_noop(self):
        factory = self.replay_flight_data('test_iam_user_credential_multi_delete_noop')
        p = self.load_policy({
            'name': 'user-cred-multi-noop',
            'resource': 'iam-user',
            'source': 'config',
            'filters': [
                {'UserName': 'test1'},
                {"type": "credential",
                 "report_max_age": 1543724277,
                 "key": "access_keys.last_rotated",
                 "value": 30,
                 'op': 'gt',
                 "value_type": "age"},
                {"type": "credential",
                 "report_max_age": 1543724277,
                 "key": "access_keys.active",
                 "value": True,
                 "op": "eq"}],
            'actions': [
                {'type': 'remove-keys',
                 'matched': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 0)
        client = factory().client('iam')
        keys = client.list_access_keys(UserName='test1').get('AccessKeyMetadata')
        self.assertEqual(len(keys), 2)

    def test_credential_access_key_reverse_filter_delete(self):
        access_key_filters = [
            {"type": "credential",
             "report_max_age": 1585865564,
             "key": "access_keys.last_used_date",
             "value": 90,
             'op': 'gte',
             "value_type": "age"},
            {"type": "credential",
             "report_max_age": 1585865564,
             "key": "access_keys.last_rotated",
             "value": 90,
             "op": "gte",
             'value_type': 'age'}]

        # Given:
        # - Two access key filters
        # - A single user with two access keys
        # - Each access key matching one filter but not the other
        #
        # Nesting the access key filters inside an 'or' block
        # should yield 2 matched keys, while the default 'and'
        # behavior should match 1.

        factory = self.replay_flight_data(
            'test_iam_user_credential_reverse_filter_delete'
        )
        p = self.load_policy({
            'name': 'user-cred-multi-reverse-or',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'zscholl'},
                {'or': access_key_filters}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 2)

        factory = self.replay_flight_data(
            'test_iam_user_credential_reverse_filter_delete'
        )
        p = self.load_policy({
            'name': 'user-cred-multi-reverse-and',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'zscholl'},
                *access_key_filters],
            'actions': [
                {'type': 'remove-keys',
                 'disable': True,
                 'matched': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 1)

    def test_access_key_last_service(self):
        # Note we're reusing the old console users flight records
        session_factory = self.replay_flight_data("test_iam_user_console_old")
        p = self.load_policy(
            {
                "name": "user-access-iam",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "credential",
                        "report_max_age": 86400 * 7,
                        "key": "access_keys.last_used_service",
                        "value": "iam",
                    }
                ],
            },
            session_factory=session_factory,
            cache=True,
        )
        with freezegun.freeze_time("2016-11-25T20:27"):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(sorted([r["UserName"] for r in resources]), ["kapil"])

    def test_old_console_users(self):
        session_factory = self.replay_flight_data("test_iam_user_console_old")
        p = self.load_policy(
            {
                "name": "old-console-only-users",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "credential",
                        "report_delay": 0.01,
                        "key": "access_keys",
                        "value": "absent",
                    },
                    {
                        "type": "credential",
                        "key": "password_last_used",
                        "value_type": "age",
                        "value": 30,
                        "op": "greater-than",
                    },
                ],
            },
            session_factory=session_factory,
            cache=True,
        )

        with freezegun.freeze_time("2016-11-25T20:27:00+00:00"):
            resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            sorted([r["UserName"] for r in resources]), ["anthony", "chrissy", "matt"]
        )

    def test_record_transform(self):
        info = {
            "access_key_2_active": "false",
            "password_next_rotation": "2017-01-24T13:15:33+00:00",
            "access_key_2_last_rotated": "N/A",
            "mfa_active": "true",
            "cert_1_active": "false",
            "cert_1_last_rotated": "N/A",
            "access_key_1_last_used_date": "N/A",
            "arn": "arn:aws:iam::644160558196:user/anthony",
            "cert_2_active": "false",
            "password_enabled": "true",
            "access_key_2_last_used_region": "N/A",
            "password_last_changed": "2016-10-26T13:15:33+00:00",
            "access_key_1_last_rotated": "N/A",
            "user_creation_time": "2016-10-06T16:11:27+00:00",
            "access_key_1_last_used_service": "N/A",
            "user": "anthony",
            "password_last_used": "2016-10-26T13:14:37+00:00",
            "cert_2_last_rotated": "N/A",
            "access_key_2_last_used_date": "N/A",
            "access_key_2_last_used_service": "N/A",
            "access_key_1_last_used_region": "N/A",
            "access_key_1_active": "false",
        }
        credential = UserCredentialReport({}, None)
        credential.process_user_record(info)
        self.assertEqual(
            info,
            {
                "arn": "arn:aws:iam::644160558196:user/anthony",
                "mfa_active": True,
                "password_enabled": True,
                "password_last_changed": "2016-10-26T13:15:33+00:00",
                "password_last_used": "2016-10-26T13:14:37+00:00",
                "password_next_rotation": "2017-01-24T13:15:33+00:00",
                "user": "anthony",
                "user_creation_time": "2016-10-06T16:11:27+00:00",
            },
        )

    def test_record_transform_with_keys(self):
        info = {
            "access_key_2_active": "false",
            "password_next_rotation": "2017-01-24T13:15:33+00:00",
            "access_key_2_last_rotated": "N/A",
            "mfa_active": "true",
            "cert_1_active": "false",
            "cert_1_last_rotated": "N/A",
            "access_key_1_last_used_date": "N/A",
            "arn": "arn:aws:iam::644160558196:user/anthony",
            "cert_2_active": "false",
            "password_enabled": "true",
            "access_key_2_last_used_region": "N/A",
            "password_last_changed": "2016-10-26T13:15:33+00:00",
            "access_key_1_last_rotated": "2019-12-04T13:22:47+00:00",
            "user_creation_time": "2016-10-06T16:11:27+00:00",
            "access_key_1_last_used_service": "N/A",
            "user": "anthony",
            "password_last_used": "2016-10-26T13:14:37+00:00",
            "cert_2_last_rotated": "N/A",
            "access_key_2_last_used_date": "N/A",
            "access_key_2_last_used_service": "N/A",
            "access_key_1_last_used_region": "N/A",
            "access_key_1_active": "false",
        }
        credential = UserCredentialReport({}, None)
        credential.process_user_record(info)
        self.assertEqual(
            info,
            {
                "access_keys": [{
                    "active": False,
                    "last_rotated": "2019-12-04T13:22:47+00:00",
                    "last_used_date": None,
                    "last_used_region": None,
                    "last_used_service": None
                }],
                "arn": "arn:aws:iam::644160558196:user/anthony",
                "mfa_active": True,
                "password_enabled": True,
                "password_last_changed": "2016-10-26T13:15:33+00:00",
                "password_last_used": "2016-10-26T13:14:37+00:00",
                "password_next_rotation": "2017-01-24T13:15:33+00:00",
                "user": "anthony",
                "user_creation_time": "2016-10-06T16:11:27+00:00",
            },
        )


class IamUserTag(BaseTest):

    def test_iam_user_actions(self):
        factory = self.replay_flight_data('test_iam_user_tags')
        p = self.load_policy({
            'name': 'iam-tag',
            'resource': 'iam-user',
            'filters': [{
                'tag:Role': 'Dev'}],
            'actions': [
                {'type': 'tag',
                 'tags': {'Env': 'Dev'}},
                {'type': 'remove-tag',
                 'tags': ['Role']},
                {'type': 'mark-for-op',
                 'op': 'delete',
                 'days': 2}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory().client('iam')
        if self.recording:
            time.sleep(1)
        user = client.get_user(UserName=resources[0]['UserName']).get('User')
        self.assertEqual(
            {t['Key']: t['Value'] for t in resources[0]['Tags']},
            {'Role': 'Dev'})
        self.assertEqual(
            {t['Key']: t['Value'] for t in user['Tags']},
            {'Env': 'Dev',
             'maid_status': 'Resource does not meet policy: delete@2019/01/25'})

    def test_iam_user_add_remove_groups(self):
        factory = self.replay_flight_data('test_iam_user_add_remove_groups')
        client = factory().client('iam')
        response = client.list_groups_for_user(UserName='Bob')
        self.assertEqual(len(response.get('Groups')), 0)
        p = self.load_policy({
            'name': 'add-remove-user',
            'resource': 'iam-user',
            'filters': [{'type': 'value', 'key': 'UserName', 'value': 'Bob'}],
            'actions': [
                {'type': 'set-groups', 'state': 'add', 'group': 'AdminGroup'}
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        response = client.list_groups_for_user(UserName='Bob')
        self.assertEqual(len(response.get('Groups')), 1)
        self.assertEqual(response.get('Groups')[0]['GroupName'], 'AdminGroup')
        p = self.load_policy({
            'name': 'add-remove-user',
            'resource': 'iam-user',
            'filters': [{'type': 'value', 'key': 'UserName', 'value': 'Bob'}],
            'actions': [
                {'type': 'set-groups', 'state': 'remove', 'group': 'AdminGroup'}
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        response = client.list_groups_for_user(UserName='Bob')
        self.assertEqual(len(response.get('Groups')), 0)


class IAMMFAFilter(BaseTest):

    def test_iam_mfa_filter(self):
        self.patch(UserMfaDevice, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_iam_mfa_filter")
        p = self.load_policy(
            {
                "name": "iam-mfa",
                "resource": "iam-user",
                "filters": [{"type": "mfa-device", "value": []}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)


@terraform('iam_role_delete', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_role_delete(test, iam_role_delete):
    session_factory = test.replay_flight_data('test_iam_role_delete')
    client = session_factory().client('iam')
    pdata = {
        'name': 'group-delete',
        'resource': 'iam-role',
        'mode': {
            'type': 'cloudtrail',
            'events': [{
                'source': 'source',
                'event': 'event',
                'ids': "RoleNames"}]
        },
        'actions': [{'type': 'delete', 'force': True}]
    }

    event = {'detail': {
        'eventName': 'event', 'eventSource': 'source',
        'RoleNames': [iam_role_delete['aws_iam_role.test_role.name']]}}
    if test.recording:
        time.sleep(3)
    p = test.load_policy(pdata, session_factory=session_factory)
    resources = p.push(event)
    assert len(resources) == 1

    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.get_role(RoleName=iam_role_delete['aws_iam_role.test_role.name'])

    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.list_instance_profiles_for_role(
            RoleName=iam_role_delete['aws_iam_role.test_role.name'])

    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.remove_role_from_instance_profile(
            RoleName=iam_role_delete['aws_iam_role.test_role.name'],
            InstanceProfileName='test_profile')

    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.delete_instance_profile(InstanceProfileName='test_profile')


class IamRoleTest(BaseTest):

    def test_iam_role_post(self):
        factory = self.replay_flight_data("test_security_hub_iam_role")
        policy = self.load_policy(
            {
                "name": "iam-role-finding",
                "resource": "iam-role",
                "filters": [{"type": "value", "key": "RoleName", "value": "app1"}],
                "actions": [
                    {
                        "type": "post-finding",
                        "severity": 10,
                        "severity_normalized": 10,
                        "types": [
                            "Software and Configuration Checks/AWS Security Best Practices"
                        ],
                    }
                ],
            },
            config={"account_id": "101010101111"},
            session_factory=factory,
        )

        resources = policy.resource_manager.get_resources(['app1'])
        self.assertEqual(len(resources), 1)
        rfinding = policy.resource_manager.actions[0].format_resource(
            resources[0])
        self.maxDiff = None
        self.assertIn('AssumeRolePolicyDocument', rfinding['Details']['AwsIamRole'])
        rfinding['Details']['AwsIamRole'].pop('AssumeRolePolicyDocument')
        self.assertEqual(rfinding, {
            'Details': {'AwsIamRole': {
                'CreateDate': '2018-05-24T13:34:59+00:00',
                'MaxSessionDuration': 3600,
                'Path': '/',
                'RoleId': 'AROAIGK7B2VUDZL4I73HK',
                'RoleName': 'app1'}},
            'Id': 'arn:aws:iam::101010101111:role/app1',
            'Partition': 'aws',
            'Region': 'us-east-1',
            'Type': 'AwsIamRole'})
        shape_validate(rfinding['Details']['AwsIamRole'], 'AwsIamRoleDetails', 'securityhub')

    def test_iam_role_inuse(self):
        session_factory = self.replay_flight_data("test_iam_role_inuse")
        self.patch(UsedIamRole, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-inuse-role",
                "resource": "iam-role",
                "filters": [{"type": "used", "state": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iam_role_unused(self):
        session_factory = self.replay_flight_data("test_iam_role_unused")
        self.patch(UnusedIamRole, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {"name": "iam-inuse-role", "resource": "iam-role", "filters": ["unused"]},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ['arn:aws:iam::644160558196:role/service-role/AmazonSageMaker-ExecutionRole-20180108T122369'])  # NOQA

        self.assertDeprecation(p, """
            policy 'iam-inuse-role'
              filters:
                unused: filter has been deprecated (use the 'used' filter with 'state' attribute)
            """)

    def test_iam_role_get_resources(self):
        session_factory = self.replay_flight_data("test_iam_role_get_resource")
        p = self.load_policy(
            {"name": "iam-role-exists", "resource": "iam-role"},
            session_factory=session_factory,
        )
        resources = p.resource_manager.get_resources(
            ['cloudcustodian-test']
        )
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['RoleId'], "AROAIGK7B2VUDZL4I73HK")

    def test_iam_role_actions(self):
        factory = self.replay_flight_data('test_iam_role_tags')
        p = self.load_policy({
            'name': 'iam-role-tag',
            'resource': 'iam-role',
            'filters': [{
                'tag:Role': 'Dev'}],
            'actions': [
                {'type': 'tag',
                 'tags': {'Env': 'Dev'}},
                {'type': 'remove-tag',
                 'tags': ['Application']},
                {'type': 'mark-for-op',
                 'op': 'delete',
                 'days': 2}
            ]
        },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory().client('iam')
        if self.recording:
            time.sleep(1)
        role = client.get_role(RoleName=resources[0]['RoleName']).get('Role')
        self.assertEqual(
            {'Role': 'Dev'},
            {t['Key']: t['Value'] for t in resources[0]['Tags'] if t['Key'] == 'Role'})
        self.assertEqual(
            {'Dev'},
            {t['Value'] for t in role['Tags'] if t['Key'] == 'Env'})
        self.assertNotIn(
            {'Application'},
            {t['Key'] for t in role['Tags']})
        self.assertEqual(
            {'maid_status': 'Resource does not meet policy: delete@2019/01/25'},
            {t['Key']: t['Value'] for t in resources[0]['Tags'] if t['Key'] == 'maid_status'})

    def test_iam_role_set_boundary(self):
        factory = self.replay_flight_data('test_iam_role_set_boundary')
        p = self.load_policy({
            'name': 'boundary',
            'resource': 'iam-role',
            'filters': [
                {'RoleName': 'accountmgr-dev'},
                {'PermissionsBoundary': 'absent'}
            ],
            'actions': [{
                'type': 'set-boundary',
                'policy': 'arn:aws:iam::644160558196:policy/BlackListIamList'
            }]},
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['RoleName'] == 'accountmgr-dev'
        if self.recording:
            time.sleep(2)
        client = factory().client('iam')
        assert client.get_role(RoleName='accountmgr-dev')[
            'Role'].get('PermissionsBoundary', {}) == {
                'PermissionsBoundaryType': 'Policy',
                'PermissionsBoundaryArn': 'arn:aws:iam::644160558196:policy/BlackListIamList',
        }

    def test_iam_role_remove_boundary(self):
        factory = self.replay_flight_data('test_iam_role_remove_boundary')
        p = self.load_policy({
            'name': 'boundary',
            'resource': 'iam-role',
            'filters': [
                {'RoleName': 'accountmgr-dev'},
                {'PermissionsBoundary': 'present'}
            ],
            'actions': [{
                'type': 'set-boundary',
                'state': 'absent',
            }]},
            session_factory=factory)
        p.resource_manager.execution_factory = MainThreadExecutor
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['RoleName'] == 'accountmgr-dev'
        if self.recording:
            time.sleep(5)
        client = factory().client('iam')
        assert client.get_role(RoleName='accountmgr-dev')[
            'Role'].get('PermissionsBoundary', {}) == {}


class IamUserTest(BaseTest):

    def test_iam_user_set_boundary(self):
        factory = self.replay_flight_data('test_iam_user_set_boundary')
        p = self.load_policy({
            'name': 'boundary',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'devbot'},
                {'PermissionsBoundary': 'absent'}],
            'actions': [{
                'type': 'set-boundary',
                'policy': 'arn:aws:iam::644160558196:policy/BlackListIamList',
            }]},
            session_factory=factory)

        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['UserName'] == 'devbot'

        if self.recording:
            time.sleep(1)
        client = factory().client('iam')
        assert client.get_user(UserName='devbot')['User'].get('PermissionsBoundary', {}) == {
            'PermissionsBoundaryType': 'Policy',
            'PermissionsBoundaryArn': 'arn:aws:iam::644160558196:policy/BlackListIamList'
        }

    def test_iam_user_boundary_remove(self):
        factory = self.replay_flight_data('test_iam_user_remove_boundary')
        p = self.load_policy({
            'name': 'boundary',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'devbot'},
                {'PermissionsBoundary': 'present'}],
            'actions': [{
                'type': 'set-boundary', 'state': 'absent'}]},
            session_factory=factory)

        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['UserName'] == 'devbot'

        if self.recording:
            time.sleep(1)
        client = factory().client('iam')
        assert client.get_user(UserName='devbot')['User'].get('PermissionsBoundary', {}) == {}

    def test_iam_user_set_policy(self):
        session_factory = self.replay_flight_data("test_iam_user_set_policy")
        client = session_factory().client("iam")

        p = self.load_policy(
            {
                "name": "iam-user-set-policy",
                "resource": "aws.iam-user",
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "attached",
                        "arn": "arn:aws:iam::123456789012:policy/my-iam-policy"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test', resources[0]['UserName'])

        policies = client.list_attached_user_policies(UserName="test")
        self.assertEqual(len(policies['AttachedPolicies']), 1)
        self.assertEqual(policies['AttachedPolicies'][0]["PolicyName"], "my-iam-policy")

        p = self.load_policy(
            {
                "name": "iam-user-set-policy",
                "resource": "aws.iam-user",
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "*"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test', resources[0]['UserName'])

        policies = client.list_attached_user_policies(UserName="test")
        self.assertEqual(len(policies['AttachedPolicies']), 0)

    def test_iam_user_usage_no_such_entity(self):
        p = self.load_policy({
            'name': 'usage-check',
            'resource': 'iam-user',
            'filters': [
                {'type': 'usage',
                 'ServiceNamespace': 'dynamodb',
                 'TotalAuthenticatedEntities': 1,
                 'poll-delay': 0.1,
                 'match-operator': 'any'}]})

        # A lot of mock to get to an error on a specific api call.
        p.resource_manager.session_factory = sf = mock.MagicMock()
        sf.region = 'us-east-1'
        sf.return_value = f = mock.MagicMock()
        f.client.return_value = c = mock.MagicMock()
        c.generate_service_last_accessed_details.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException',
                       'Message': 'MonkeyWrench'}},
            'generate_service_last_accessed_details')
        c.exceptions.NoSuchEntityException = ClientError

        resources = p.resource_manager.filter_resources(
            [{'UserName': 'Kapil', 'Arn': 'arn:x'}])
        self.assertEqual(resources, [])

    def test_iam_user_usage(self):
        factory = self.replay_flight_data('test_iam_user_usage')
        p = self.load_policy({
            'name': 'usage-check',
            'resource': 'iam-user',
            'mode': {
                'type': 'cloudtrail',
                'events': [{'event': '', 'source': '', 'ids': 'ids'}]},
            'filters': [
                {'UserName': 'kapil'},
                {'type': 'usage',
                 'ServiceNamespace': 'dynamodb',
                 'TotalAuthenticatedEntities': 1,
                 'poll-delay': 0.1,
                 'match-operator': 'any'}]}, session_factory=factory)
        resources = p.push({'detail': {
            'eventName': '', 'eventSource': '', 'ids': ['kapil']}}, None)
        self.assertEqual(len(resources), 1)

    def test_iam_user_check_permissions_validation(self):
        invalid_actions = ['', '*', ':', 'iam', 's3:', ':GetObject']
        valid_actions = ['*:*', 's3:GetObject', 'iam:GetUser']

        def _policy_with_action(action):
            return {
                "name": "check-permissions-test-policy",
                "resource": "aws.iam-user",
                'filters': [{'type': 'check-permissions', 'match': 'allowed', 'actions': [action]}],
            }

        for action in invalid_actions:
            self.assertRaises(PolicyValidationError, self.load_policy, _policy_with_action(action))

        for action in valid_actions:
            p = self.load_policy(_policy_with_action(action))
            p.validate()

    def test_iam_user_check_permissions(self):
        factory = self.replay_flight_data('test_iam_user_check_permissions')
        p = self.load_policy({
            'name': 'perm-check',
            'resource': 'iam-user',
            'mode': {
                'type': 'cloudtrail',
                'events': [{'event': '', 'source': '', 'ids': 'ids'}],
            },
            'filters': [
                {'UserName': 'kapil'},
                {'type': 'check-permissions',
                 'match': {'EvalDecision': 'allowed'},
                 'actions': ['sqs:CreateUser']}]},
            session_factory=factory)
        resources = p.push({'detail': {
            'eventName': '', 'eventSource': '', 'ids': ['kapil']}}, None)
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:perm-matches' in resources[0])

    @functional
    def test_iam_user_delete(self):
        # To get this test to work against live AWS I had to attach the
        # following explicit policy.  Even root accounts don't work
        # without this policy:
        #
        # {
        #     "Version": "2012-10-17",
        #     "Statement": [{
        #         "Effect": "Allow",
        #         "Action": ["iam:*"],
        #         "Resource": "*"
        #     }]
        # }

        factory = self.replay_flight_data("test_iam_user_delete")
        name = "alice"
        client = factory().client("iam")
        client.create_user(UserName=name, Path="/test/")
        p = self.load_policy(
            {
                "name": "iam-user-delete",
                "resource": "iam-user",
                "filters": [{"UserName": name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        users = client.list_users(PathPrefix="/test/").get("Users", [])
        self.assertEqual(users, [])

    def test_iam_user_access_key_multi_chain(self):
        factory = self.replay_flight_data(
            'test_iam_user_access_key_multi_chain')
        p = self.load_policy({
            'name': 'key-chain',
            'resource': 'iam-user',
            'source': 'config',
            'query': [
                {'clause': "resourceId = 'AIDAIFSHVFT46NXYGWMEI'"}],
            'filters': [
                {'type': 'access-key',
                 'key': 'Status',
                 'value': 'Active'},
                {'type': 'access-key',
                 'match-operator': 'and',
                 'value_type': 'age',
                 'key': 'CreateDate',
                 'op': 'greater-than',
                 'value': 10000},
            ],
            'actions': [
                {'type': 'remove-keys',
                 'matched': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:AccessKeys']), 2)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 1)
        self.assertEqual(
            resources[0]['c7n:matched-keys'][0]['AccessKeyId'],
            'AKIAI5PSD5WUP3AO2OPA')

    def test_iam_user_access_key_multi(self):
        factory = self.replay_flight_data('test_iam_user_access_key_multi')
        p = self.load_policy({
            'name': 'user-del',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'kapil'},
                {'type': 'access-key', 'key': 'Status', 'value': 'Active'},
                {'type': 'access-key', 'key': 'CreateDate',
                 'value_type': 'age', 'value': 90, 'op': 'greater-than'}
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-keys']), 1)
        self.assertEqual(
            resources[0]['c7n:matched-keys'][0]['c7n:match-type'], 'access')

    def test_iam_user_ssh_key_filter(self):
        factory = self.replay_flight_data('test_iam_user_ssh_key_filter')
        p = self.load_policy({
            'name': 'iam-user-old-ssh-keys',
            'source': 'config',
            'query': [
                {'clause': "resourceName = 'test3'"},
            ],
            'resource': 'iam-user',
            'filters': [
                {'type': 'ssh-key', 'key': 'Status', 'value': 'Active'},
                {'type': 'ssh-key', 'key': 'UploadDate',
                 'value_type': 'age', 'value': 90, 'op': 'greater-than'},
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-ssh-keys']), 1)

    def test_iam_user_delete_ssh_keys(self):
        factory = self.replay_flight_data('test_iam_user_delete_ssh_keys')
        user_name = 'test2'
        p = self.load_policy({
            'name': 'iam-user-delete-ssh-keys',
            'resource': 'iam-user',
            'source': 'config',
            'query': [
                {'clause': "resourceName = 'test2'"},
            ],
            'filters': [
                {'type': 'ssh-key', 'key': 'Status', 'value': 'Active'},
            ],
            'actions': [
                {'type': 'delete-ssh-keys'},
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-ssh-keys']), 1)
        client = p.session_factory().client('iam')
        keys = client.list_ssh_public_keys(UserName=user_name)['SSHPublicKeys']
        self.assertEqual(len(keys), 0)

    def test_iam_user_delete_some_access(self):
        # TODO: this test could use a rewrite
        factory = self.replay_flight_data("test_iam_user_delete_options")
        p = self.load_policy(
            {
                "name": "iam-user-delete",
                "resource": "iam-user",
                "filters": [
                    {"UserName": "test_user"},
                    {"type": "access-key", "key": "Status", "value": "Active"},
                    {"type": "credential", "report_max_age": 1543724277,
                     "key": "password_enabled", "value": True}],
                "actions": [{
                    "type": "delete",
                    "options": ["console-access", "access-keys"]}],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        resources = p.run()
        self.assertFalse(resources)

        p = self.load_policy(
            {
                "name": "iam-user-delete",
                "resource": "iam-user",
                "filters": [{"UserName": "test_user"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iam_user_policy(self):
        session_factory = self.replay_flight_data("test_iam_user_admin_policy")
        self.patch(UserPolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-user-policy",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "policy",
                        "key": "PolicyName",
                        "value": "AdministratorAccess",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["UserName"], "alphabet_soup")

    def test_iam_user_policy_include_via(self):
        session_factory = self.replay_flight_data("test_iam_user_admin_policy_include_via")
        self.patch(UserPolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-user-policy",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "policy",
                        "key": "PolicyName",
                        "value": "AdministratorAccess",
                        "include-via": True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["UserName"], "alphabet_soup_1")
        self.assertEqual(len(resources[0]["c7n:Policies"]), 2)
        self.assertEqual(resources[1]["UserName"], "alphabet_soup_2")
        self.assertEqual(len(resources[1]["c7n:Policies"]), 2)

    def test_iam_user_access_key_filter(self):
        session_factory = self.replay_flight_data("test_iam_user_access_key_active")
        self.patch(UserAccessKey, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-user-with-key",
                "resource": "iam-user",
                "filters": [{"type": "access-key", "key": "Status", "value": "Active"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["UserName"], "alphabet_soup")

    def test_iam_user_login_profile(self):
        session_factory = self.replay_flight_data('test_iam_user_login_profile')
        p = self.load_policy(
            {
                "name": "iam-users-with-console-access",
                "resource": "iam-user",
                "filters": [{"type": "login-profile"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["UserName"], "test-user-console-access")


@terraform('iam_user', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_user_disable_ssh_keys(test, iam_user):
    factory = test.replay_flight_data('test_iam_user_disable_ssh_keys')
    username = iam_user['aws_iam_user.user.name']

    if test.recording:
        time.sleep(5)

    p = test.load_policy({
        'name': 'iam-user-ssh-keys',
        'resource': 'iam-user',
        'filters': [
            {
                'type': 'value',
                'key': 'UserName',
                'value': username
            },
            {'type': 'ssh-key', 'key': 'Status', 'value': 'Active'},
        ],
        'actions': [
            {'type': 'delete-ssh-keys', 'disable': True, 'matched': True},
        ]},
        session_factory=factory)

    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(len(resources[0]['c7n:matched-ssh-keys']), 1)

    client = p.session_factory().client('iam')
    keys = client.list_ssh_public_keys(UserName=username)['SSHPublicKeys']
    test.assertTrue(all(
        key['Status'] == 'Inactive' for key in keys
    ))


class IamUserGroupMembership(BaseTest):

    def test_iam_user_group_membership(self):
        session_factory = self.replay_flight_data("test_iam_user_group_membership")
        self.patch(GroupMembership, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-admin-users",
                "resource": "iam-user",
                "filters": [{"type": "group", "key": "GroupName", "value": "QATester"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["UserName"], "kapil")
        self.assertTrue(resources[0]["c7n:Groups"])


class IamInstanceProfileFilterUsage(BaseTest):

    def test_iam_instance_profile_inuse(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_inuse")
        self.patch(UsedInstanceProfiles, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-inuse-profiles",
                "resource": "iam-profile",
                "filters": ["used"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ['arn:aws:iam::644160558196:instance-profile/root_joshua'])

    def test_iam_instance_profile_unused(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_unused")
        self.patch(UnusedInstanceProfiles, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-unused-profiles",
                "resource": "iam-profile",
                "filters": ["unused"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Arn"], "arn:aws:iam::644160558196:instance-profile/mandeep")
        self.assertEqual(resources[0]["InstanceProfileName"], "mandeep")


class IamInstanceProfileActions(BaseTest):

    def test_iam_instance_profile_set_role(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_set_role")
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-role",
                "resource": "iam-profile",
                "actions": [
                    {"type": "set-role", "role": "my-test-role"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        instance_profiles = client.list_instance_profiles()
        for profile in instance_profiles['InstanceProfiles']:
            self.assertEqual(profile['Roles'][0]['RoleName'], 'my-test-role')

    def test_iam_instance_profile_set_role_remove(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_set_role_remove")
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-role-remove",
                "resource": "iam-profile",
                "actions": [
                    {"type": "set-role", "role": ""}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        instance_profiles = client.list_instance_profiles()
        for profile in instance_profiles['InstanceProfiles']:
            self.assertEqual(len(profile['Roles']), 0)

    def test_iam_instance_profile_set_policy_attached(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_set_policy_attached")
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-policy",
                "resource": "iam-profile",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "has-specific-managed-policy",
                                "key": "PolicyArn",
                                "value": "arn:aws:iam::aws:policy/AdministratorAccess"
                            }
                        ],
                    },
                    {
                        "type": "value",
                        "key": "Roles[].RoleName",
                        "value": "AmazonSSMRoleForInstancesQuickSetup",
                        "op": "in",
                        "value_type": "swap"
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "attached",
                        "arn": "arn:aws:iam::aws:policy/AdministratorAccess"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        instance_profiles = client.list_instance_profiles()
        for profile in instance_profiles['InstanceProfiles']:
            if profile['Roles'][0]['RoleName'] == "AmazonSSMRoleForInstancesQuickSetup":
                policies = client.list_attached_role_policies(
                        RoleName="AmazonSSMRoleForInstancesQuickSetup"
                )
                self.assertEqual(len(policies['AttachedPolicies']), 1)
                self.assertEqual(
                        policies['AttachedPolicies'][0]["PolicyName"], "AdministratorAccess"
                )

    def test_iam_instance_profile_set_policy_detached(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_set_policy_detached")
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-policy",
                "resource": "iam-profile",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "key": "PolicyArn",
                        "value": "arn:aws:iam::aws:policy/AdministratorAccess"
                    },
                    {
                        "type": "value",
                        "key": "Roles[].RoleName",
                        "value": "AmazonSSMRoleForInstancesQuickSetup",
                        "op": "in",
                        "value_type": "swap"
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "arn:aws:iam::aws:policy/AdministratorAccess"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        instance_profiles = client.list_instance_profiles()
        for profile in instance_profiles['InstanceProfiles']:
            if profile['Roles'][0]['RoleName'] == "AmazonSSMRoleForInstancesQuickSetup":
                policies = client.list_attached_role_policies(
                        RoleName="AmazonSSMRoleForInstancesQuickSetup"
                )
                self.assertEqual(len(policies['AttachedPolicies']), 0)

    def test_iam_instance_profile_set_policy_wildcard(self):
        session_factory = self.replay_flight_data("test_iam_instance_profile_set_policy_wildcard")
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-policy",
                "resource": "iam-profile",
                "filters": [
                    {
                        "type": "value",
                        "key": "Roles[].RoleName",
                        "value": "AmazonSSMRoleForInstancesQuickSetup",
                        "op": "in",
                        "value_type": "swap"
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "*"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        instance_profiles = client.list_instance_profiles()
        for profile in instance_profiles['InstanceProfiles']:
            if profile['Roles'][0]['RoleName'] == "AmazonSSMRoleForInstancesQuickSetup":
                policies = client.list_attached_role_policies(
                        RoleName="AmazonSSMRoleForInstancesQuickSetup"
                )
                self.assertEqual(len(policies['AttachedPolicies']), 0)

    def test_iam_instance_profile_set_policy_nosuchentity(self):
        session_factory = self.replay_flight_data(
            "test_iam_instance_profile_set_policy_nosuchentity"
        )
        client = session_factory().client("iam")
        p = self.load_policy(
            {
                "name": "iam-instance-profile-set-policy",
                "resource": "iam-profile",
                "filters": [
                    {
                        "type": "value",
                        "key": "Roles[].RoleName",
                        "value": "AmazonSSMRoleForInstancesQuickSetup",
                        "op": "in",
                        "value_type": "swap"
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "arn:aws:iam::aws:policy/AdministratorAccessDoesNotExist"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(
            client.exceptions.NoSuchEntityException,
            client.get_policy,
            PolicyArn="arn:aws:iam::aws:policy/AdministratorAccessDoesNotExist")


class IamPolicyFilterUsage(BaseTest):

    def test_iam_user_policy_permission(self):
        session_factory = self.replay_flight_data('test_iam_policy_check_permission')
        p = self.load_policy({
            'name': 'iam-policy-check',
            'resource': 'iam-policy',
            'mode': {'type': 'cloudtrail', 'events': [
                {'ids': 'ids', 'source': '', 'event': ''}]},
            'filters': [
                {'type': 'check-permissions',
                 'match': 'allowed',
                 'actions': ['ecr:PutImage']}]},
            session_factory=session_factory)
        resources = p.push({'detail': {
            'eventName': '', 'eventSource': '',
            'ids': ["arn:aws:iam::644160558196:policy/service-role/codebuild-policy"]}},
            None)
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:policy' in resources[0])
        self.assertTrue('c7n:perm-matches' in resources[0])

    def test_iam_policy_get_resources(self):
        session_factory = self.replay_flight_data("test_iam_policy_get_resource")
        p = self.load_policy(
            {"name": "iam-attached-profiles", "resource": "iam-policy"},
            session_factory=session_factory,
        )
        resources = p.resource_manager.get_resources(
            ["arn:aws:iam::aws:policy/AWSHealthFullAccess"]
        )
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["PolicyName"], "AWSHealthFullAccess")

    def test_iam_attached_policies(self):
        session_factory = self.replay_flight_data("test_iam_policy_attached")
        self.patch(UsedIamPolicies, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-attached-profiles",
                "resource": "iam-policy",
                "filters": ["used"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 6)

    def test_iam_unattached_policies(self):
        session_factory = self.replay_flight_data("test_iam_policy_unattached")
        self.patch(UnusedIamPolicies, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-attached-profiles",
                "resource": "iam-policy",
                "filters": ["unused"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class IamPolicy(BaseTest):

    def test_iam_policy_delete(self):
        factory = self.replay_flight_data('test_iam_policy_delete')
        p = self.load_policy({
            'name': 'delete-policy',
            'resource': 'iam-policy',
            'query': [{'Name': 'Scope', 'Value': 'Local'}],
            'filters': [
                {'AttachmentCount': 0},
                {'type': 'value', 'key': 'DefaultVersionId', 'value': 'v1', 'op': 'ne'},
            ],
            'actions': ['delete']},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['PolicyName'], 'IamCreateRoleAndCreatePolicy')

        if self.recording:
            time.sleep(3)

        client = factory().client('iam')
        self.assertRaises(
            client.exceptions.NoSuchEntityException,
            client.get_policy,
            PolicyArn=resources[0]['Arn'])

    def test_iam_query_parser(self):
        qfilters = [
            {'Name': 'Scope', 'Value': 'Local'},
            {'Name': 'OnlyAttached', 'Value': True}]

        self.assertEqual(qfilters, PolicyQueryParser.parse(qfilters))
        self.assertRaises(
            PolicyValidationError,
            PolicyQueryParser.parse,
            {'Name': 'Scope', 'Value': ['All', 'Local']})

    def test_iam_has_allow_all_policies(self):
        session_factory = self.replay_flight_data("test_iam_policy_allow_all")
        self.patch(UnusedIamPolicies, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-has-allow-all",
                "resource": "iam-policy",
                "filters": [
                    {
                        "type": "value",
                        "key": "PolicyName",
                        "value": "MyAdminPolicy",
                    },
                    "has-allow-all",
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


@terraform('iam_user_group', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_group_delete(test, iam_user_group):
    session_factory = test.replay_flight_data('test_iam_group_delete')
    client = session_factory().client('iam')

    pdata = {
        'name': 'group-delete',
        'resource': 'iam-group',
        'mode': {
            'type': 'cloudtrail',
            'events': [{
                'source': 'source',
                'event': 'event',
                'ids': "GroupNames"}]
        },
        'actions': ['delete']
    }
    event = {'detail': {
        'eventName': 'event', 'eventSource': 'source',
        'GroupNames': [iam_user_group['aws_iam_group.sandbox_devs.name']]}}

    if test.recording:
        time.sleep(3)

    p = test.load_policy(pdata, session_factory=session_factory)
    with pytest.raises(ClientError) as ecm:
        p.push(event)
    assert ecm.value.response[
        'Error']['Code'] == 'DeleteConflict'

    pdata['actions'] = [{'type': 'delete', 'force': True}]

    p = test.load_policy(pdata, session_factory=session_factory)
    resources = p.push(event)
    assert len(resources) == 1

    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.get_group(GroupName=resources[0]['GroupName'])


# The terraform fixture sets up resources, which happens before we
# actually enter the test:
@terraform('iam_delete_provider_oidc', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_delete_provider_oidc_action(test, iam_delete_provider_oidc):
    # The 'iam_delete_provider_oidc' argument allows us to access the
    # data in the 'tf_resources.json' file inside the
    # 'tests/terraform/iam_delete_provider_oidc' directory.  Here's how
    # we access the IAM provider's arn using a 'dotted' notation:
    arn = iam_delete_provider_oidc['aws_iam_openid_connect_provider.test_oidc_provider.arn']

    # Uncomment to following line when you're recording the first time:
    # session_factory = test.record_flight_data('iam_delete_provider_oidc')

    # If you already recorded the interaction with AWS for this test,
    # you can just replay it.  In which case, the files containing the
    # responses from AWS are gonna be found inside the
    # 'tests/data/placebo/iam_delete_provider_oidc' directory:
    session_factory = test.replay_flight_data('iam_delete_provider_oidc')

    # Set up an 'iam' boto client for the test:
    client = session_factory().client('iam')

    # Execute the 'delete' action that we want to test:
    pdata = {
        'name': 'delete',
        'resource': 'iam-oidc-provider',
        'filters': [
            {
                'type': 'value',
                'key': 'Url',
                'value': 'accounts.google.com',
            },
        ],
        'actions': [
            {
                'type': 'delete',
            },
        ],
    }
    policy = test.load_policy(pdata, session_factory=session_factory)
    resources = policy.run()

    # Here's the number of resources that the policy resolved,
    # i.e. the resources that passed the filters:
    assert len(resources) == 1
    assert resources[0]['Arn'] == arn

    # We're testing that our delete action worked because the iam
    # provider now no longer exists:
    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.get_open_id_connect_provider(OpenIDConnectProviderArn=arn)


# The terraform fixture sets up resources, which happens before we
# actually enter the test:
@terraform('iam_delete_provider_saml', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_delete_provider_saml_action(test, iam_delete_provider_saml):
    # The 'iam_delete_provider_saml' argument allows us to access the
    # data in the 'tf_resources.json' file inside the
    # 'tests/terraform/iam_delete_provider_saml' directory.  Here's how
    # we access the IAM provider's arn using a 'dotted' notation:
    arn = iam_delete_provider_saml['aws_iam_saml_provider.test_saml_provider.arn']

    # Uncomment to following line when you're recording the first time:
    # session_factory = test.record_flight_data('iam_delete_provider_saml')

    # If you already recorded the interaction with AWS for this test,
    # you can just replay it.  In which case, the files containing the
    # responses from AWS are gonna be found inside the
    # 'tests/data/placebo/iam_delete_provider_saml' directory:
    session_factory = test.replay_flight_data('iam_delete_provider_saml')

    # Set up an 'iam' boto client for the test:
    client = session_factory().client('iam')

    # Execute the 'delete' action that we want to test:
    pdata = {
        'name': 'delete',
        'resource': 'iam-saml-provider',
        'filters': [
            {
                'type': 'value',
                'key': 'tag:Name',
                'value': 'testprovider',
            },
        ],
        'actions': [
            {
                'type': 'delete',
            },
        ],
    }
    policy = test.load_policy(pdata, session_factory=session_factory)
    resources = policy.run()

    # Here's the number of resources that the policy resolved,
    # i.e. the resources that passed the filters:
    assert len(resources) == 1
    assert resources[0]['Arn'] == arn

    # We're testing that our delete action worked because the iam
    # provider now no longer exists:
    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.get_saml_provider(SAMLProviderArn=arn)


# The terraform fixture sets up resources, which happens before we
# actually enter the test:
@terraform('iam_delete_certificate', teardown=terraform.TEARDOWN_IGNORE)
def test_iam_delete_certificate_action(test, iam_delete_certificate):
    # The 'iam_delete_certificate' argument allows us to access the
    # data in the 'tf_resources.json' file inside the
    # 'tests/terraform/iam_delete_certificate' directory.  Here's how
    # we access the cert's name using a 'dotted' notation:
    iam_cert_name = iam_delete_certificate['aws_iam_server_certificate.test_cert_alt.name']
    iam_cert_arn = iam_delete_certificate['aws_iam_server_certificate.test_cert_alt.arn']

    # Uncomment to following line when you're recording the first time:
    # session_factory = test.record_flight_data('iam_delete_certificate')

    # If you already recorded the interaction with AWS for this test,
    # you can just replay it.  In which case, the files containing the
    # responses from AWS are gonna be found inside the
    # 'tests/data/placebo/iam_delete_certificate' directory:
    session_factory = test.replay_flight_data('iam_delete_certificate')

    # Set up an 'iam' boto client for the test:
    client = session_factory().client('iam')

    # Execute the 'delete' action that we want to test:
    pdata = {
        'name': 'delete',
        'resource': 'iam-certificate',
        'filters': [
            {
                'type': 'value',
                'key': 'ServerCertificateName',
                'value': iam_cert_name,
                'op': 'eq',
            },
        ],
        'actions': [
            {
                'type': 'delete',
            },
        ],
    }
    policy = test.load_policy(pdata, session_factory=session_factory)
    resources = policy.run()

    # Here's the number of resources that the policy resolved,
    # i.e. the resources that passed the filters:
    assert len(resources) == 1
    assert resources[0]['Arn'] == iam_cert_arn

    # We're testing that our delete action worked because the iam
    # certificate now no longer exists:
    with pytest.raises(client.exceptions.NoSuchEntityException):
        client.get_server_certificate(ServerCertificateName=iam_cert_name)


class IamGroupTests(BaseTest):

    def test_iam_group_used_users(self):
        session_factory = self.replay_flight_data("test_iam_group_used_users")
        self.patch(IamGroupUsers, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-group-used",
                "resource": "iam-group",
                "filters": [{"type": "has-users", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            p.resource_manager.get_arns(resources),
            ['arn:aws:iam::644160558196:group/Admins',
             'arn:aws:iam::644160558196:group/powerusers'])

    def test_iam_group_unused_users(self):
        session_factory = self.replay_flight_data("test_iam_group_unused_users")
        self.patch(IamGroupUsers, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-group-unused",
                "resource": "iam-group",
                "filters": [{"type": "has-users", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iam_group_get_resources(self):
        session_factory = self.replay_flight_data("test_iam_group_get_resource")
        p = self.load_policy(
            {"name": "iam-group-exists", "resource": "iam-group"},
            session_factory=session_factory,
        )
        resources = p.resource_manager.get_resources(
            ["ServiceCatalogUsers"]
        )
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], "AGPAI6NICSNT546VPVZGS")

    def test_iam_group_with_managed_policy(self):
        session_factory = self.replay_flight_data("test_iam_group_with_managed_policy")
        p = self.load_policy(
            {
                "name": "iam-groups-have-ses-send-policy",
                "resource": "aws.iam-group",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "value": "AmazonSESFullAccess"
                    }
                ]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iam_group_set_policy(self):
        session_factory = self.replay_flight_data("test_iam_group_set_policy")
        client = session_factory().client("iam")

        p = self.load_policy(
            {
                "name": "iam-group-set-policy",
                "resource": "aws.iam-group",
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "attached",
                        "arn": "arn:aws:iam::123456789012:policy/my-iam-policy"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test', resources[0]['GroupName'])

        policies = client.list_attached_group_policies(GroupName="test")
        self.assertEqual(len(policies['AttachedPolicies']), 1)
        self.assertEqual(policies['AttachedPolicies'][0]["PolicyName"], "my-iam-policy")

        p = self.load_policy(
            {
                "name": "iam-group-set-policy",
                "resource": "aws.iam-group",
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "*"
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test', resources[0]['GroupName'])

        policies = client.list_attached_group_policies(GroupName="test")
        self.assertEqual(len(policies['AttachedPolicies']), 0)


class IamManagedPolicyUsage(BaseTest):

    def test_iam_role_has_specific_managed_policy(self):
        session_factory = self.replay_flight_data(
            "test_iam_role_no_specific_managed_policy"
        )
        self.patch(SpecificIamRoleManagedPolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-role-with-specific-managed-policy",
                "resource": "iam-role",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "value": "TestForSpecificMP",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_iam_role_no_specific_managed_policy(self):
        session_factory = self.replay_flight_data(
            "test_iam_role_no_specific_managed_policy"
        )
        self.patch(
            NoSpecificIamRoleManagedPolicy, "executor_factory", MainThreadExecutor
        )
        p = self.load_policy(
            {
                "name": "iam-role-no-specific-managed-policy",
                "resource": "iam-role",
                "filters": [
                    {
                        "type": "no-specific-managed-policy",
                        "value": "DoesNotExistPolicy",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)


class IamInlinePolicyUsage(BaseTest):

    def test_iam_user_has_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_user_has_inline_policy")
        self.patch(IamUserInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-user-with-inline-policy",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "value",
                        "key": "UserName",
                        "op": "in",
                        "value": ["andrewalexander", "kapil", "scot@sixfeetup.com"],
                    },
                    {"type": "has-inline-policy", "value": True},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["UserName"], "kapil")
        self.assertEqual(resources[0]["c7n:InlinePolicies"][0],
            "policygen-andrewalexander-201612112039")

    def test_iam_user_no_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_user_no_inline_policy")
        self.patch(IamUserInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-user-without-inline-policy",
                "resource": "iam-user",
                "filters": [
                    {
                        "type": "value",
                        "key": "UserName",
                        "op": "in",
                        "value": ["andrewalexander", "kapil", "scot@sixfeetup.com"],
                    },
                    {"type": "has-inline-policy", "value": False},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["UserName"] for r in resources]),
            ["andrewalexander", "scot@sixfeetup.com"],
        )
        self.assertFalse(resources[0]["c7n:InlinePolicies"])

    def test_iam_role_has_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_role_has_inline_policy")
        self.patch(IamRoleInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-role-with-inline-policy",
                "resource": "iam-role",
                "filters": [{"type": "has-inline-policy", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n:InlinePolicies'][0],
            "oneClick_lambda_basic_execution_1466943062384")

    def test_iam_role_no_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_role_has_inline_policy")
        self.patch(IamRoleInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-role-without-inline-policy",
                "resource": "iam-role",
                "filters": [{"type": "has-inline-policy", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertFalse(resources[0]["c7n:InlinePolicies"])

    def test_iam_group_has_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_group_has_inline_policy")
        self.patch(IamGroupInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-group-with-inline-policy",
                "resource": "iam-group",
                "filters": [{"type": "has-inline-policy", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n:InlinePolicies'][0],
            "Access-Key-and-Read-Only-Access")

    def test_iam_group_has_inline_policy2(self):
        session_factory = self.replay_flight_data("test_iam_group_has_inline_policy")
        self.patch(IamGroupInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-group-with-inline-policy",
                "resource": "iam-group",
                "filters": [{"type": "has-inline-policy"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n:InlinePolicies'][0],
            "Access-Key-and-Read-Only-Access")

    def test_iam_group_no_inline_policy(self):
        session_factory = self.replay_flight_data("test_iam_group_no_inline_policy")
        self.patch(IamGroupInlinePolicy, "executor_factory", MainThreadExecutor)
        p = self.load_policy(
            {
                "name": "iam-group-without-inline-policy",
                "resource": "iam-group",
                "filters": [{"type": "has-inline-policy", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertFalse(resources[0]["c7n:InlinePolicies"])

    def test_iam_group_delete_inline_policies(self):
        session_factory = self.replay_flight_data("test_iam_group_delete_inline_policies")
        p = self.load_policy(
            {
                "name": "iam-delete-group-policies",
                "resource": "aws.iam-group",
                "actions": [{
                    "type": "delete-inline-policies"
                }],
            },
            session_factory=session_factory,
        )
        resources = {r["GroupName"]: r for r in p.run()}
        noncompliant_group = "test1"
        self.assertIn(noncompliant_group, resources)
        self.assertEqual(len(resources[noncompliant_group]["c7n:InlinePolicies"]), 1)

        client = session_factory().client("iam")
        inline_policies_after = client.list_group_policies(GroupName=noncompliant_group)
        self.assertEqual(len(inline_policies_after["PolicyNames"]), 0)


class GlacierCrossAccount(BaseTest):

    def test_glacier_cross_account(self):
        self.patch(CrossAccountAccessFilter, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_cross_account_glacier")
        client = session_factory().client("glacier")
        name = "c7n-cross-check"

        url = client.create_vault(vaultName=name)["location"]
        self.addCleanup(client.delete_vault, vaultName=name)

        account_id = url.split("/")[1]
        arn = "arn:aws:glacier:%s:%s:vaults/%s" % (
            os.environ.get("AWS_DEFAULT_REGION", "us-east-1"), account_id, name
        )

        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "glacier:UploadArchive",
                    "Resource": arn,
                    "Effect": "Allow",
                    "Principal": "*",
                }
            ],
        }

        client.set_vault_access_policy(
            vaultName=name, policy={"Policy": json.dumps(policy)}
        )

        p = self.load_policy(
            {
                "name": "glacier-cross",
                "resource": "glacier",
                "filters": ["cross-account"],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VaultName"], name)


LAMBDA_SRC = """\
def handler(event, context):
    return {'Success': True}
"""


class LambdaCrossAccount(BaseTest):

    role = "arn:aws:iam::644160558196:role/lambda_basic_execution"

    def test_lambda_cross_account(self):
        self.patch(CrossAccountAccessFilter, "executor_factory", MainThreadExecutor)

        session_factory = self.replay_flight_data("test_cross_account_lambda")
        client = session_factory().client("lambda")
        name = "c7n-cross-check"

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, tmp_dir)
        archive = PythonPackageArchive()
        archive.add_contents("handler.py", LAMBDA_SRC)
        archive.close()

        func = LambdaFunction(
            {
                "runtime": "python2.7",
                "name": name,
                "description": "",
                "handler": "handler.handler",
                "memory_size": 128,
                "timeout": 5,
                "role": self.role,
            },
            archive,
        )
        manager = LambdaManager(session_factory)
        manager.publish(func)
        self.addCleanup(manager.remove, func)

        client.add_permission(
            FunctionName=name,
            StatementId="oops",
            Principal="*",
            Action="lambda:InvokeFunction",
        )

        p = self.load_policy(
            {
                "name": "lambda-cross",
                "resource": "lambda",
                "filters": ["cross-account"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FunctionName"], name)


class ECRCrossAccount(BaseTest):

    @functional
    def test_ecr_cross_account(self):
        session_factory = self.replay_flight_data("test_cross_account_ecr")
        client = session_factory().client("ecr")
        repo_name = "c7n/cross-check"

        client.create_repository(repositoryName=repo_name)["repository"]
        self.addCleanup(client.delete_repository, repositoryName=repo_name)

        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {"Action": "ecr:BatchGetImage", "Effect": "Allow", "Principal": "*"}
            ],
        }

        client.set_repository_policy(
            repositoryName=repo_name, policyText=json.dumps(policy)
        )

        p = self.load_policy(
            {"name": "ecr-cross", "resource": "ecr", "filters": ["cross-account"]},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["repositoryName"], repo_name)


class SQSCrossAccount(BaseTest):

    def test_sqs_cross_account(self):

        session_factory = self.replay_flight_data("test_cross_account_sqs")
        client = session_factory().client("sqs")
        queue_name = "c7n-cross-check"
        url = client.create_queue(QueueName=queue_name)["QueueUrl"]
        self.addCleanup(client.delete_queue, QueueUrl=url)
        account_id = url.split("/")[3]
        arn = "arn:aws:sqs:%s:%s:%s" % (
            os.environ.get("AWS_DEFAULT_REGION", "us-east-1"), account_id, queue_name
        )

        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "SQS:SendMessage",
                    "Effect": "Allow",
                    "Resource": arn,
                    "Principal": "*",
                }
            ],
        }

        client.set_queue_attributes(
            QueueUrl=url, Attributes={"Policy": json.dumps(policy)}
        )

        p = self.load_policy(
            {"name": "sqs-cross", "resource": "sqs", "filters": ["cross-account"]},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["QueueUrl"], url)


class SNSCrossAccount(BaseTest):

    def test_sns_cross_account(self):
        self.patch(SNS, "executor_factory", MainThreadExecutor)

        session_factory = self.replay_flight_data("test_cross_account_sns")
        client = session_factory().client("sns")
        topic_name = "c7n-cross-check"
        arn = client.create_topic(Name=topic_name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=arn)

        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "SNS:Publish",
                    "Effect": "Allow",
                    "Resource": arn,
                    "Principal": "*",
                }
            ],
        }

        client.set_topic_attributes(
            TopicArn=arn, AttributeName="Policy", AttributeValue=json.dumps(policy)
        )

        p = self.load_policy(
            {"name": "sns-cross", "resource": "sns", "filters": ["cross-account"]},
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TopicArn"], arn)

    @functional
    def test_sns_cross_account_endpoint_condition(self):
        self.patch(SNS, "executor_factory", MainThreadExecutor)

        session_factory = self.replay_flight_data(
            "test_cross_account_sns_endpoint_condition"
        )
        client = session_factory().client("sns")
        topic_name = "c7n-endpoint-condition-test"
        arn = client.create_topic(Name=topic_name)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=arn)

        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "SNS:Publish",
                    "Effect": "Allow",
                    "Resource": arn,
                    "Principal": "*",
                    "Condition": {
                        "StringLike": {"SNS:Endpoint": "@capitalone.com"},
                        "StringEquals": {"AWS:SourceOwner": "644160558196"},
                    },
                }
            ],
        }

        client.set_topic_attributes(
            TopicArn=arn, AttributeName="Policy", AttributeValue=json.dumps(policy)
        )

        p = self.load_policy(
            {
                "name": "sns-cross",
                "resource": "sns",
                "filters": [{"TopicArn": arn}, "cross-account"],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "sns-cross",
                "resource": "sns",
                "filters": [
                    {"TopicArn": arn},
                    {
                        "type": "cross-account",
                        "whitelist_endpoints": ["@whitelist.com"],
                        "whitelist_conditions": ["aws:UserName"]
                    },
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)


class CrossAccountChecker(TestCase):

    def test_not_principal_allowed(self):
        policy = {
            "Id": "Foo",
            "Version": "2012-10-17",
            "Statement": [
                {"Action": "SQS:ReceiveMessage", "Effect": "Deny", "Principal": "*"},
                {
                    "Action": "SQS:SendMessage",
                    "Effect": "Allow",
                    "NotPrincipal": "90120",
                },
            ],
        }

        checker = PolicyChecker({"allowed_accounts": {"221800032964"}})

        self.assertTrue(bool(checker.check(policy)))

    def test_sqs_policies(self):
        policies = load_data("iam/sqs-policies.json")

        checker = PolicyChecker({"allowed_accounts": {"221800032964"}})
        for p, expected in zip(
            policies, [False, True, True, False, False, False, False, False]
        ):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_iam_policies(self):
        policies = load_data("iam/iam-policies.json")

        checker = PolicyChecker({
            "allowed_accounts": [
                "111111111111",
                "cognito-identity.amazonaws.com",
            ]
        })
        for p, expected in zip(
            policies, [False, True, True, False, False, True]
        ):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_principal_org_id(self):
        statements = [
            {'Actions': ['Deploy', 'UnshareApplication'],
             'Principal': ['*'],
             'StatementId': 'cab89702-05f0-4751-818e-ced6e98ef5f9',
             'Effect': 'Allow',
             'Condition': {
                 'StringEquals': {
                     'aws:PrincipalOrgID': ['o-4pmkskbcf9']}}},
            {'Actions': ['Deploy'],
             'Principal': ['619193117841'],
             'StatementId': 'b364d84f-62d2-411c-9787-3636b2b1975c',
             'Effect': 'Allow'}
        ]

        checker = PolicyChecker({
            'allowed_orgid': ['o-4pmkskbcf9']})

        for statement, expected in zip(statements, [False, True]):
            self.assertEqual(
                bool(checker.handle_statement(statement)), expected)

        checker = PolicyChecker({})
        for statement, expected in zip(statements, [True, True]):
            self.assertEqual(
                bool(checker.handle_statement(statement)), expected)

    def test_s3_policies(self):
        policies = load_data("iam/s3-policies.json")
        checker = PolicyChecker(
            {
                "allowed_accounts": {"123456789012"},
                "allowed_vpc": {"vpc-12345678"},
                "allowed_vpce": {"vpce-12345678", "vpce-87654321"},
            }
        )
        for p, expected in zip(
            policies,
            [
                True,
                False,
                False,
                True,
                False,
                True,
                False,
                True,
                False,
                True,
                False,
                True,
                False,
                True,
            ],
        ):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_policies_vpc(self):
        policies = load_data("iam/s3-policies.json")
        checker = PolicyChecker({"allowed_accounts": {"123456789012"}})
        for p, expected in zip(
            policies,
            [
                True,
                False,
                False,
                True,
                False,
                True,
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                True,
            ],
        ):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_policies_multiple_conditions(self):
        policies = load_data("iam/s3-conditions.json")
        checker = PolicyChecker(
            {
                "allowed_accounts": {"123456789012"},
                "allowed_vpc": {"vpc-12345678"},
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_everyone_only(self):
        policies = load_data("iam/s3-principal.json")
        checker = PolicyChecker({"everyone_only": True})
        for p, expected in zip(policies, [True, True, False, False, False, False]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_return_allowed_only(self):
        policies = load_data("iam/s3-principal.json")
        checker = PolicyChecker({"return_allowed": True})
        for p, expected in zip(policies, [False, False, False, True, True, True]):
            allowances = checker.check(p)
            self.assertEqual(bool(allowances), expected)

    def test_s3_principal_org_id(self):
        policies = load_data("iam/s3-orgid.json")
        checker = PolicyChecker(
            {
                "allowed_orgid": {"o-goodorg"}
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_policies_multiple_keys(self):
        policies = load_data("iam/s3-condition-multi-keys.json")
        checker = PolicyChecker(
            {
                "allowed_accounts": {"123456789012"},
                "allowed_orgid": {"o-goodorg"}
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_resource_org_id(self):
        policies = load_data("iam/s3-resource-orgid.json")
        checker = PolicyChecker(
            {
                "allowed_orgid": {"o-goodorg"}
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)
        checker = PolicyChecker(
            {
                "allowed_orgid": {}
            }
        )
        for p, expected in zip(policies, [True, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_arn_condition(self):
        policies = load_data("iam/s3-arn-conditions.json")
        checker = PolicyChecker(
            {
                "allowed_accounts": {"123456789012"}
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)
        checker = PolicyChecker(
            {
                "allowed_accounts": {}
            }
        )
        for p, expected in zip(policies, [True, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_principal_account(self):
        policies = load_data("iam/s3-principal-accounts.json")
        checker = PolicyChecker(
            {
                "allowed_accounts": {"123456789012"}
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)
        checker = PolicyChecker(
            {
                "allowed_accounts": {}
            }
        )
        for p, expected in zip(policies, [True, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)


class SetRolePolicyAction(BaseTest):
    def test_set_policy_attached(self):
        factory = self.replay_flight_data("test_iam_set_policy_attached")

        p = self.load_policy(
            {
                "name": "iam-attach-role-policy",
                "resource": "iam-role",
                "filters": [
                    {
                        "type": "no-specific-managed-policy",
                        "value": "my-iam-policy",
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "attached",
                        "arn": "arn:aws:iam::123456789012:policy/my-iam-policy",
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test-role-us-east-1', resources[0]['RoleName'])

    def test_set_policy_detached(self):
        factory = self.replay_flight_data("test_iam_set_policy_detached")

        p = self.load_policy(
            {
                "name": "iam-attach-role-policy",
                "resource": "iam-role",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "value": "my-iam-policy",
                    }
                ],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "arn:aws:iam::123456789012:policy/my-iam-policy",
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test-role-us-east-1', resources[0]['RoleName'])


class SAMLProviderTests(BaseTest):

    def test_saml_provider(self):
        factory = self.replay_flight_data('test_saml_provider')
        p = self.load_policy({
            'name': 'aws-saml',
            'resource': 'aws.iam-saml-provider'},
            session_factory=factory)

        resources = p.run()
        assert len(resources) == 1
        self.assertJmes(
            'IDPSSODescriptor.SingleSignOnService[0].Location',
            resources[0],
            'https://portal.sso.us-east-1.amazonaws.com/saml/assertion/MDMwNTk1ODQ3MDk5X2lucy')


class DeleteRoleAction(BaseTest):

    @functional
    def test_delete_role(self):
        factory = self.replay_flight_data("test_delete_role")
        policy_doc = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }]
        })
        client = factory().client("iam")
        client.create_role(
            RoleName="c7n-test-delete", AssumeRolePolicyDocument=policy_doc, Path='/pratyush/',
            Tags=[{'Key': 'Name', 'Value': 'pratyush'}])
        p = self.load_policy(
            {
                'name': 'iam-attach-role-policy',
                'resource': 'iam-role',
                'filters': [{'tag:Name': 'pratyush'}],
                "actions": ["delete"],
            },
            session_factory=factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(ClientError, client.get_role, RoleName=resources[0]['RoleName'])

    def test_set_policy_wildcard(self):
        factory = self.replay_flight_data("test_set_policy_wildcard")
        policy = self.load_policy(
            {
                'name': 'iam-force-delete-role',
                'resource': 'iam-role',
                'filters': [{'tag:Name': 'Pratyush'}],
                "actions": [
                    {
                        "type": "set-policy",
                        "state": "detached",
                        "arn": "*",
                    }
                ]
            },
            session_factory=factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("iam")
        self.assertEqual(
            len((client.list_attached_role_policies(RoleName=resources[0]['RoleName']))
            ['AttachedPolicies']), 0)

    def test_set_policy_validation_error(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "iam-policy-error",
                "resource": "iam-role",
                'filters': [{'tag:Name': 'Pratyush'}],
                "actions": [{"type": "set-policy", "state": "attached", "arn": "*"}],
            }
        )

    def test_set_policy_arn_construction(self):
        factory = self.replay_flight_data("test_set_policy_arn_construction")

        # Use set-policy with an explicit ARN
        p = self.load_policy(
            {
                "name": "iam-policy-error",
                "resource": "iam-role",
                "source": "config",
                "query": [{"clause": "resourceName = 'custodian-testing'"}],
                "actions": [{
                    "type": "set-policy",
                    "state": "attached",
                    "arn": "arn:aws:iam::{account_id}:policy/DeleteMe"
                }],
            },
            session_factory=factory
        )
        p.expand_variables(p.get_variables())
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(1)

        # Use a policy name
        p = self.load_policy(
            {
                "name": "iam-policy-error",
                "resource": "iam-role",
                "source": "config",
                "query": [{"clause": "resourceName = 'custodian-testing'"}],
                "filters": [{"type": "has-specific-managed-policy", "value": "DeleteMe"}],
                "actions": [{"type": "set-policy", "state": "detached", "arn": "DeleteMe"}],
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_force_delete_role(self):
        factory = self.replay_flight_data("test_force_delete_role")
        policy = self.load_policy(
            {
                'name': 'iam-force-delete-role',
                'resource': 'iam-role',
                'filters': [{'tag:Name': 'Pratyush'}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("iam")
        self.assertRaises(ClientError, client.get_role, RoleName=resources[0]['RoleName'])

    def test_delete_role_error(self):
        factory = self.replay_flight_data("test_delete_role_error")
        p = self.load_policy(
            {
                'name': 'iam-delete-profile-roles',
                'resource': 'iam-role',
                'filters': [{'tag:Name': 'CannotDelete'}],
                "actions": ["delete"],
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("iam")
        self.assertTrue(
            client.get_role(RoleName=resources[0]['RoleName']), 'AWSServiceRoleForSupport')


class TestIamProfileHasSpecificManagedPolicyFilter(BaseTest):

    def test_iam_profile_has_specific_managed_policy_filter(self):
        factory = self.replay_flight_data("test_iam_profile_has_specific_managed_policy")
        p = self.load_policy(
            {
                "name": "iam-profile-has-admin-policy",
                "resource": "iam-profile",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "value": "admin-policy",
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
