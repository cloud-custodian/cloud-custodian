# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

from botocore.exceptions import ClientError
from pytest_terraform import terraform

from c7n.resources import cw

from .common import BaseTest


@terraform('cloudwatch_dashboard_tag')
def test_cloudwatch_dashboard_tag(test, cloudwatch_dashboard_tag):
    # Dashboards are tagged through the native cloudwatch apis, the
    # resource groups tagging api rejects their region-less arns.
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_cloudwatch_dashboard_tag', region=aws_region)

    dashboard_name = cloudwatch_dashboard_tag[
        'aws_cloudwatch_dashboard.test.dashboard_name']

    p = test.load_policy({
        'name': 'dashboard-tag',
        'resource': 'aws.cloudwatch-dashboard',
        'filters': [{'DashboardName': dashboard_name}],
        'actions': [
            {'type': 'tag', 'tags': {'App': 'Custodian', 'Env': 'Dev'}}]},
        session_factory=session_factory, config={'region': aws_region})
    resources = p.run()
    test.assertEqual(len(resources), 1)

    client = session_factory().client('cloudwatch')
    arn = resources[0]['DashboardArn']
    test.assertEqual(
        {t['Key']: t['Value']
         for t in client.list_tags_for_resource(ResourceARN=arn)['Tags']},
        {'App': 'Custodian', 'Env': 'Dev'})

    # filtering on the tag we just set exercises the read path - these
    # tags aren't visible through the resource groups tagging api.
    p = test.load_policy({
        'name': 'dashboard-remove-tag',
        'resource': 'aws.cloudwatch-dashboard',
        'filters': [
            {'DashboardName': dashboard_name},
            {'tag:App': 'Custodian'}],
        'actions': [{'type': 'remove-tag', 'tags': ['Env']}]},
        session_factory=session_factory, config={'region': aws_region})
    resources = p.run()
    test.assertEqual(len(resources), 1)

    test.assertEqual(
        client.list_tags_for_resource(ResourceARN=arn)['Tags'],
        [{'Key': 'App', 'Value': 'Custodian'}])


def _client_error(code):
    return ClientError({'Error': {'Code': code, 'Message': code}}, 'Operation')


class CloudWatchDashboardTest(BaseTest):

    def get_source(self):
        p = self.load_policy({
            'name': 'dashboard-augment',
            'resource': 'aws.cloudwatch-dashboard'})
        return p.resource_manager.source

    def test_augment_skips_deleted_dashboard(self):
        source = self.get_source()
        client = mock.MagicMock()
        client.list_tags_for_resource.side_effect = [
            _client_error('ResourceNotFoundException'),
            {'Tags': [{'Key': 'App', 'Value': 'Custodian'}]},
        ]
        dashboards = [
            {'DashboardName': 'gone',
             'DashboardArn': 'arn:aws:cloudwatch::644160558196:dashboard/gone'},
            {'DashboardName': 'here',
             'DashboardArn': 'arn:aws:cloudwatch::644160558196:dashboard/here'},
        ]
        with mock.patch.object(cw, 'local_session') as ls:
            ls.return_value.client.return_value = client
            resources = source.augment(dashboards)
        self.assertEqual(
            [r['DashboardName'] for r in resources], ['here'])
        self.assertEqual(
            resources[0]['Tags'], [{'Key': 'App', 'Value': 'Custodian'}])

    def test_augment_error(self):
        source = self.get_source()
        client = mock.MagicMock()
        client.list_tags_for_resource.side_effect = _client_error('AccessDeniedException')
        with mock.patch.object(cw, 'local_session') as ls:
            ls.return_value.client.return_value = client
            with self.assertRaises(ClientError):
                source.augment([
                    {'DashboardName': 'here',
                     'DashboardArn': 'arn:aws:cloudwatch::644160558196:dashboard/here'}])
