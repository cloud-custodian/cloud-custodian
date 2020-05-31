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
import json
import datetime
import os
import mock
import tempfile
import time

from unittest import TestCase
from .common import load_data, BaseTest, functional
from .test_offhours import mock_datetime_now

from dateutil import parser

from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.filters.iamaccess import CrossAccountAccessFilter, PolicyChecker, HasStatementChecker
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
                 "value": 700,
                 "op": "greater-than",
                 'value_type': 'age'}],
            'actions': [
                {'type': 'remove-keys',
                 'matched': True}]},
            session_factory=factory)
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

    def test_credential_access_key_reverse_filter_delete(self):
        factory = self.replay_flight_data(
            'test_iam_user_credential_reverse_filter_delete'
        )
        p = self.load_policy({
            'name': 'user-cred-multi-reverse',
            'resource': 'iam-user',
            'filters': [
                {'UserName': 'zscholl'},
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
                 'value_type': 'age'}],
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
        with mock_datetime_now(parser.parse("2016-11-25T20:27:00+00:00"), datetime):
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

        with mock_datetime_now(parser.parse("2016-11-25T20:27:00+00:00"), datetime):
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
            ['arn:aws:iam::644160558196:role/service-role/AmazonSageMaker-ExecutionRole-20180108T122369']) # NOQA

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
                 'tags': ['Application']}
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
                 'value': 400},
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
        self.assertEqual(len(resources), 2)


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
        self.assertEqual(len(resources), 7)

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
        self.assertEqual(len(resources), 202)


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
                        "value": "AdministratorAccess",
                    },
                    "has-allow-all",
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class IamGroupFilterUsage(BaseTest):

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


class KMSCrossAccount(BaseTest):

    def test_kms_cross_account(self):
        self.patch(CrossAccountAccessFilter, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_cross_account_kms")
        client = session_factory().client("kms")

        policy = {
            "Id": "Lulu",
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Enable IAM User Permissions",
                    "Effect": "Allow",
                    "Principal": {"AWS": "arn:aws:iam::644160558196:root"},
                    "Action": "kms:*",
                    "Resource": "*",
                },
                {
                    "Sid": "Enable Cross Account",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "kms:Encrypt",
                    "Resource": "*",
                },
            ],
        }

        key_info = client.create_key(
            Policy=json.dumps(policy), Description="test-cross-account-3"
        )[
            "KeyMetadata"
        ]

        # disable and schedule deletion
        self.addCleanup(
            client.schedule_key_deletion, KeyId=key_info["KeyId"], PendingWindowInDays=7
        )
        self.addCleanup(client.disable_key, KeyId=key_info["KeyId"])

        p = self.load_policy(
            {
                "name": "kms-cross",
                "resource": "kms-key",
                "filters": [{"KeyState": "Enabled"}, "cross-account"],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["KeyId"], key_info["KeyId"])


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

    def test_sqs_has_statements(self):

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
                    "Condition": {
                        "StringNotEquals": {
                            "aws:PrincipalOrgID": "o-4amkskbcf1"
                        }
                    }
                }
            ],
        }

        client.set_queue_attributes(
            QueueUrl=url, Attributes={"Policy": json.dumps(policy)}
        )

        p = self.load_policy(
            {
                "name": "sqs-has_statements",
                "resource": "aws.sqs",
                "filters": [
                    {"QueueArn": "arn:aws:sqs:us-west-2:644160558196:c7n-cross-check"},
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": "SQS:SendMessage",
                                "Condition": {
                                    "StringNotEquals": {
                                        "aws:PrincipalOrgID": "o-4amkskbcf1"
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert(
            "\"Effect\":\"Allow\",\"Principal\":\"*\",\"Action\":\"SQS:SendMessage\""
            in resources[0]["Policy"]
        )
        assert(
            "\"Condition\":{\"StringNotEquals\":{\"aws:PrincipalOrgID\":\"o-4amkskbcf1\"}}"
            in resources[0]["Policy"]
        )


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
                    },
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_sns_has_statements(self):
        session_factory = self.replay_flight_data(
            "test_cross_account_sns_endpoint_condition"
        )
        p = self.load_policy(
            {
                "name": "sns-cross",
                "resource": "sns",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Principal": "*",
                                "Condition": {
                                    "StringEquals": {"AWS:SourceOwner": "644160558196"},
                                },
                                "PartialMatch": "Condition"
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert(
            "\"Effect\":\"Allow\",\"Principal\":\"*\""
            in resources[0]["Policy"]
        )
        assert(
            "{\"AWS:SourceOwner\":\"644160558196\"}"
            in resources[0]["Policy"]
        )


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


class HasStatementCheckerTests(TestCase):

    def test_s3_policies_multiple_conditions(self):
        policies = load_data("iam/s3-conditions.json")
        checker = HasStatementChecker(
            {
                "statements": [
                    {
                        "Condition": {
                            "ArnLike": {
                                "aws:SourceArn": "arn:aws:sns:us-east-1:123456789012"
                            },
                            "StringEquals": {
                                "aws:sourceVpc": "vpc-55252554"
                            }
                        }
                    }
                ]
            }
        )
        for p, expected in zip(policies, [False, True]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_principal_star(self):
        policies = load_data("iam/s3-principal.json")
        checker = HasStatementChecker(
            {
                "statements": [
                    {
                        "Principal": "*",
                        "PartialMatch": "Principal"
                    }
                ]
            }
        )
        for p, expected in zip(policies, [True, True, False, True, True, False]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_s3_principal_org_id(self):
        policies = load_data("iam/s3-orgid.json")
        checker = HasStatementChecker(
            {
                "statements": [
                    {
                        "Condition": {
                            "StringEquals": {
                                "aws:PrincipalOrgID": "o-goodorg"
                            }
                        }
                    }
                ]
            }
        )
        for p, expected in zip(policies, [True, False]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)

    def test_has_statement_variations(self):
        policies = load_data("iam/has-statement-variations.json")
        checker = HasStatementChecker(
            {
                "statements": [
                    {
                        "Effect": "Allow",
                        "Action": "sns:Subscribe",
                        "Resource": "arn:aws:sns:us-east-2:644160558196:MyTopic",
                        "Condition": {
                            "StringEquals": {
                                "sns:Protocol": [
                                    "https"
                                ]
                            }
                        },
                        "PartialMatch": [
                            "Condition"
                        ]
                    }
                ]
            }
        )
        for p, expected in zip(policies, [True, False]):
            violations = checker.check(p)
            self.assertEqual(bool(violations), expected)
        checker.checker_config['statements'] = [
            {
                "Effect": "Deny",
                "Action": "glue:*",
                "Principal": "*",
                "Resource": "arn:aws:glue:us-east-1:644160558196:*",
                "Condition": {
                    "StringNotEquals": {
                        "aws:PrincipalOrgId": 'o-4amkskbcf1'
                    }
                }
            }
        ]
        for p, expected in zip(policies, [False, True]):
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
