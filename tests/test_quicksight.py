# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform
from c7n.exceptions import ClientError
from tests.zpill import ACCOUNT_ID

from .common import BaseTest
from c7n.utils import local_session
from botocore.exceptions import ClientError


@terraform("quicksight_group")
def test_quicksight_group_query(test, quicksight_group):
    factory = test.replay_flight_data("test_quicksight_group_query")

    policy = test.load_policy({
      "name": "test-aws-quicksight-group",
      "resource": "aws.quicksight-group"
    }, session_factory=factory, config={'account_id': '490065885863'})

    resources = policy.run()
    assert len(resources) > 0
    assert resources[0]['GroupName'] == 'tf-example'


@terraform("quicksight_dashboard")
def test_quicksight_dashboard(test, quicksight_dashboard):
    session_factory = test.replay_flight_data("test_quicksight_dashboard")
    client = session_factory().client("quicksight")
    policy = test.load_policy({
        "name": "test-aws-quicksight-dashboards",
        'resource': 'aws.quicksight-dashboard',
        'filters': [
            {'tag:Owner': 'c7n'},
        ],
    }, session_factory=session_factory, config={'account_id': ACCOUNT_ID})

    resources = policy.run()
    test.assertEqual(len(resources), 1)

    arn = resources[0]['Arn']
    tags = client.list_tags_for_resource(ResourceArn=arn)["Tags"]
    test.assertEqual(tags, resources[0]['Tags'])


@terraform("quicksight_datasource")
def test_quicksight_datasource(test, quicksight_datasource):
    session_factory = test.replay_flight_data("test_quicksight_datasource")
    client = session_factory().client("quicksight")
    policy = test.load_policy({
        "name": "test-aws-quicksight-datasource",
        'resource': 'aws.quicksight-datasource',
        'filters': [
            {'tag:Owner': 'c7n'},
        ],
    }, session_factory=session_factory, config={'account_id': ACCOUNT_ID})

    resources = policy.run()
    test.assertEqual(len(resources), 1)

    arn = resources[0]['Arn']
    tags = client.list_tags_for_resource(ResourceArn=arn)["Tags"]
    test.assertEqual(tags, resources[0]['Tags'])


@terraform("quicksight_dashboard")
def test_quicksight_dashboard_resource_not_found(test, quicksight_dashboard):
    """Test that ResourceNotFoundException during tag fetch is handled gracefully."""

    session_factory = test.replay_flight_data("test_quicksight_dashboard")

    policy = test.load_policy({
        "name": "test-aws-quicksight-dashboard-not-found",
        'resource': 'aws.quicksight-dashboard',
        'source': 'describe',
    }, session_factory=session_factory, config={'account_id': ACCOUNT_ID})

    # Mock the list_tags_for_resource to raise ResourceNotFoundException
    original_client = session_factory().client

    def mock_client(service_name, *args, **kwargs):
        client = original_client(service_name, *args, **kwargs)
        if service_name == 'quicksight':

            def mock_list_tags(*args, **kwargs):
                error_response = {'Error': {'Code': 'ResourceNotFoundException'}}
                raise ClientError(error_response, 'ListTagsForResource')

            client.list_tags_for_resource = mock_list_tags
        return client

    session_factory().client = mock_client

    resources = policy.run()
    # Should not crash and should set Tags to empty list
    test.assertGreater(len(resources), 0)
    test.assertEqual(resources[0]['Tags'], [])


class TestQuicksight(BaseTest):

    def test_quicksight_account_query(self):
        factory = self.replay_flight_data("test_quicksight_account_query")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account",
            "filters": [{"PublicSharingEnabled": False}]
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_quicksight_account_get_account_not_found(self):
        factory = self.replay_flight_data("test_quicksight_account_not_found")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account"
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources, [])

    def test_quicksight_account_from_non_identity_region(self):
        factory = self.replay_flight_data("test_quicksight_account_from_non_identity_region")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account"
        }, session_factory=factory, config={'region': 'us-west-2'})

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_quicksight_account_standard_edition(self):
        factory = self.replay_flight_data("test_quicksight_account_standard_edition")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account",
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources, [])

    def test_quicksight_account_raise_client_error(self):
        # Simulate a client error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_account_raise_client_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account",
        }, session_factory=factory)

        with self.assertRaises(ClientError):
            policy.run()

    def test_quicksight_account_raise_server_error(self):
        # Simulate a server error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_account_raise_server_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-account",
            "resource": "aws.quicksight-account",
        }, session_factory=factory)

        with self.assertRaises(Exception):
            policy.run()

    def test_quicksight_user_query(self):
        factory = self.replay_flight_data("test_quicksight_user_query")

        policy = self.load_policy({
            "name": "test-aws-quicksight-user",
            "resource": "aws.quicksight-user"
        }, session_factory=factory)

        resources = policy.run()
        self.assertGreater(len(resources), 0)
        self.assertIn('UserName', resources[0])

    def test_quicksight_user_delete(self):
        factory = self.replay_flight_data("test_quicksight_user_delete")

        policy = self.load_policy({
            "name": "test-aws-quicksight-user-delete",
            "resource": "aws.quicksight-user",
            "actions": [{"type": "delete"}]
        }, session_factory=factory)

        resources = policy.run()
        self.assertGreater(len(resources), 0)
        self.assertIn('UserName', resources[0])

        client = local_session(factory).client('quicksight')
        users = client.list_users(
            AwsAccountId=self.account_id,
            Namespace='default'
        )["UserList"]
        self.assertEqual(len(users), 0)

    def test_quicksight_dashboard_standard_edition(self):
        factory = self.replay_flight_data("test_quicksight_dashboard_standard_edition")

        policy = self.load_policy({
            "name": "test-aws-quicksight-dashboard",
            "resource": "aws.quicksight-dashboard",
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources, [])

    def test_quicksight_dashboard_raise_client_error(self):
        # Simulate a client error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_dashboard_raise_client_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-dashboard",
            "resource": "aws.quicksight-dashboard",
        }, session_factory=factory)

        with self.assertRaises(ClientError):
            policy.run()

    def test_quicksight_dashboard_raise_server_error(self):
        # Simulate a server error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_dashboard_raise_server_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-dashboard",
            "resource": "aws.quicksight-dashboard",
        }, session_factory=factory)

        with self.assertRaises(Exception):
            policy.run()

    def test_quicksight_datasource_standard_edition(self):
        factory = self.replay_flight_data("test_quicksight_datasource_standard_edition")

        policy = self.load_policy({
            "name": "test-aws-quicksight-datasource",
            "resource": "aws.quicksight-datasource",
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources, [])

    def test_quicksight_group_standard_edition(self):
        factory = self.replay_flight_data("test_quicksight_group_standard_edition")

        policy = self.load_policy({
            "name": "test-aws-quicksight-group",
            "resource": "aws.quicksight-group",
        }, session_factory=factory)

        resources = policy.run()
        self.assertEqual(resources, [])

    def test_quicksight_group_raise_client_error(self):
        # Simulate a client error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_group_raise_client_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-group",
            "resource": "aws.quicksight-group",
        }, session_factory=factory)

        with self.assertRaises(ClientError):
            policy.run()

    def test_quicksight_group_raise_server_error(self):
        # Simulate a server error from the service and ensure it is raised
        factory = self.replay_flight_data("test_quicksight_group_raise_server_error")

        policy = self.load_policy({
            "name": "test-aws-quicksight-group",
            "resource": "aws.quicksight-group",
        }, session_factory=factory)

        with self.assertRaises(Exception):
            policy.run()
