# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Unexpected ClientErrors must surface, not be swallowed.

Each of these sites handles one expected error code (the resource went away,
the snapshot is in use, ...) and used to drop every other error silently,
which reads as success and in some cases carried the previous loop
iteration's result over to the next resource.
"""
from unittest import mock

from botocore.exceptions import ClientError

from c7n.resources import account, ami, apigw, iam, s3

from .common import BaseTest


def client_error(code='AccessDenied', op='Operation'):
    return ClientError({'Error': {'Code': code, 'Message': code}}, op)


def session_with(**clients):
    session = mock.MagicMock()
    session.client.side_effect = lambda name, *a, **kw: clients[name]
    return lambda factory, *a, **kw: session


class UnexpectedClientErrorTest(BaseTest):

    def test_ec2_user_data(self):
        p = self.load_policy({
            'name': 'ec2-user-data', 'resource': 'ec2',
            'filters': [{'type': 'user-data', 'op': 'regex', 'value': '.*'}]})
        f = p.resource_manager.filters[0]
        client = mock.MagicMock()
        client.describe_instance_attribute.side_effect = [
            {'UserData': {'Value': 'IyEvYmluL2Jhc2g='}}, client_error()]
        first, second = {'InstanceId': 'i-1'}, {'InstanceId': 'i-2'}
        with self.assertRaises(ClientError):
            f.process_instance_set(client, [first, second])
        # the second instance must not inherit the first one's user data
        self.assertNotIn(f.annotation, second)

    def test_ec2_user_data_not_found_skipped(self):
        p = self.load_policy({
            'name': 'ec2-user-data', 'resource': 'ec2',
            'filters': [{'type': 'user-data', 'op': 'regex', 'value': '.*'}]})
        f = p.resource_manager.filters[0]
        client = mock.MagicMock()
        client.describe_instance_attribute.side_effect = client_error(
            'InvalidInstanceId.NotFound')
        self.assertEqual(f.process_instance_set(client, [{'InstanceId': 'i-1'}]), [])

    def test_account_check_cloudtrail_metric_filters(self):
        p = self.load_policy({
            'name': 'account-trail', 'resource': 'account',
            'filters': [{'type': 'check-cloudtrail', 'running': False,
                         'log-metric-filter-pattern': 'ConsoleLogin'}]})
        f = p.resource_manager.filters[0]
        cloudtrail, logs = mock.MagicMock(), mock.MagicMock()
        cloudtrail.describe_trails.return_value = {'trailList': [{
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:123456789012:trail/t',
            'CloudWatchLogsLogGroupArn':
                'arn:aws:logs:us-east-1:123456789012:log-group:trail-logs:*'}]}
        logs.get_paginator.return_value.paginate.return_value.build_full_result.side_effect = (
            client_error())
        self.patch(account, 'local_session', session_with(
            cloudtrail=cloudtrail, logs=logs,
            cloudwatch=mock.MagicMock(), sns=mock.MagicMock()))
        with self.assertRaises(ClientError):
            f.process([{'account_id': '123456789012'}])

    def test_apigw_rest_integration(self):
        p = self.load_policy({
            'name': 'rest-integration', 'resource': 'rest-resource',
            'filters': [{'type': 'rest-integration', 'key': 'type', 'value': 'AWS'}]})
        f = p.resource_manager.filters[0]
        client = mock.MagicMock()
        client.get_integration.side_effect = client_error()
        with self.assertRaises(ClientError):
            f.process_task_set(client, [({'restApiId': 'a', 'id': 'r'}, 'GET')])
        client.get_integration.side_effect = client_error('NotFoundException')
        self.assertEqual(
            f.process_task_set(client, [({'restApiId': 'a', 'id': 'r'}, 'GET')]), [])

    def test_apigw_domain_update_security(self):
        p = self.load_policy({
            'name': 'domain-tls', 'resource': 'apigw-domain-name',
            'actions': [{'type': 'update-security', 'securityPolicy': 'TLS_1_2'}]})
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        client.update_domain_name.side_effect = client_error('BadRequestException')
        self.patch(apigw.utils, 'local_session', session_with(apigateway=client))
        with self.assertRaises(ClientError):
            action.process([{'domainName': 'example.com'}])

    def test_ami_deregister_snapshot_delete(self):
        p = self.load_policy({
            'name': 'ami-deregister', 'resource': 'ami',
            'actions': [{'type': 'deregister', 'delete-snapshots': True}]},
            config={'account_id': '123456789012'})
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        client.delete_snapshot.side_effect = client_error()
        self.patch(ami, 'local_session', session_with(ec2=client))
        image = {'ImageId': 'ami-1', 'OwnerId': '123456789012',
                 'BlockDeviceMappings': [{'Ebs': {'SnapshotId': 'snap-1'}}]}
        with self.assertRaises(ClientError):
            action.process([image])
        client.delete_snapshot.side_effect = client_error('InvalidSnapshot.InUse')
        action.process([image])

    def test_iam_policy_get_resources(self):
        p = self.load_policy({'name': 'iam-policy', 'resource': 'iam-policy'})
        client = mock.MagicMock()
        client.get_policy.side_effect = client_error('Throttling')
        self.patch(iam, 'local_session', session_with(iam=client))
        arn = 'arn:aws:iam::123456789012:policy/p'
        with self.assertRaises(ClientError):
            p.resource_manager.source.get_resources([arn])
        # the manager reports unresolved ids instead of passing silently
        with self.assertLogs(p.resource_manager.log, level='WARNING') as logs:
            self.assertEqual(p.resource_manager.get_resources([arn]), [])
        self.assertIn('Throttling', logs.output[0])
        client.get_policy.side_effect = client_error('NoSuchEntityException')
        self.assertEqual(
            p.resource_manager.get_resources(['arn:aws:iam::123456789012:policy/p']), [])

    def test_s3_delete_global_grants(self):
        p = self.load_policy({
            'name': 's3-grants', 'resource': 's3',
            'actions': [{'type': 'delete-global-grants'}]})
        action = p.resource_manager.actions[0]
        client = mock.MagicMock()
        client.put_bucket_acl.side_effect = client_error()
        self.patch(s3, 'bucket_client', lambda session, b, *a, **kw: client)
        self.patch(p.resource_manager, 'session_factory', mock.MagicMock())
        bucket = {
            'Name': 'b', 'Website': None,
            'Acl': {'Owner': {'ID': 'o'}, 'Grants': [{
                'Grantee': {'URI': 'http://acs.amazonaws.com/groups/global/AllUsers'},
                'Permission': 'READ'}]}}
        with self.assertRaises(ClientError):
            action.process_bucket(bucket)
        client.put_bucket_acl.side_effect = client_error('NoSuchBucket')
        self.assertIsNone(action.process_bucket(bucket))
