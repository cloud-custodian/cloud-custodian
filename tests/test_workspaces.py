# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import time
from dateutil import parser
from mock import patch

from .common import BaseTest
from c7n import filters
from c7n.executor import MainThreadExecutor
from c7n.resources.workspaces import Workspace
from c7n.exceptions import PolicyExecutionError
from c7n.testing import mock_datetime_now
from c7n.utils import annotation

# Define constants
TEST_WORKSPACE_NAME = 'test-workspace'
TEST_WORKSPACE_TAG = 'test-tag'
TEST_WORKSPACE_TAG_VALUE = 'test-tag-value'
TEST_WORKSPACE_BUNDLE_NAME = 'test-bundle'
TEST_WORKSPACE_DIRECTORY_ID = 'd-90675153fc'

class WorkspacesTest(BaseTest):

    def setUp(self):
        # Initialize resources
        pass

    def tearDown(self):
        # Clean up resources
        pass

    def _load_policy(self, policy, session_factory):
        try:
            p = self.load_policy(policy, session_factory=session_factory)
            return p.run()
        except Exception as e:
            self.fail(f"Test failed with exception: {e}")

    def test_workspaces_query_returns_three_resources(self):
        """Test querying Workspaces resources returns three resources."""
        session_factory = self.replay_flight_data("test_workspaces_query")
        resources = self._load_policy(
            {
                "name": TEST_WORKSPACE_NAME,
                "resource": "workspaces"
            }, session_factory
        )
        self.assertEqual(len(resources), 3)

    def test_workspaces_tags_filter_returns_two_resources(self):
        """Test filtering Workspaces resources by tags returns two resources."""
        self.patch(Workspace, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_workspaces_query")
        resources = self._load_policy(
            {
                "name": "workspaces-tag-test",
                "resource": "workspaces",
                "filters": [
                    {"tag:Environment": "sandbox"}
                ]
            },
            config={'account_id': '644160558196'},
            session_factory=session_factory
        )
        self.assertEqual(len(resources), 2)

    def test_connection_status_filter_returns_one_resource(self):
        """Test filtering Workspaces resources by connection status returns one resource."""
        session_factory = self.replay_flight_data("test_workspaces_connection_status")
        resources = self._load_policy(
            {
                "name": "workspaces-connection-status",
                "resource": "workspaces",
                "filters": [{
                    "type": "connection-status",
                    "value_type": "age",
                    "key": "LastKnownUserConnectionTimestamp",
                    "op": "ge",
                    "value": 30
                }]
            }, session_factory=session_factory
        )
        with mock_datetime_now(parser.parse("2019-04-13T00:00:00+00:00"), datetime):
            self.assertEqual(len(resources), 1)
            self.assertIn('LastKnownUserConnectionTimestamp',
                annotation(resources[0], filters.ANNOTATION_KEY))

    def test_workspaces_kms_filter_returns_one_resource(self):
        """Test filtering Workspaces resources by KMS key returns one resource."""
        session_factory = self.replay_flight_data('test_workspaces_kms_filter')
        kms = session_factory().client('kms')
        resources = self._load_policy(
            {
                'name': 'test-workspaces-kms-filter',
                'resource': 'workspaces',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/aws/workspaces'
                    }
                ]
            },
            session_factory=session_factory
        )
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['VolumeEncryptionKey'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/workspaces')

    def test_workspaces_terminate(self):
        """Test terminating Workspaces resources."""
        session_factory = self.replay_flight_data('test_workspaces_terminate')
        resources = self._load_policy(
            {
                'name': 'workspaces-terminate',
                'resource': 'workspaces',
                'filters': [{
                    'tag:DeleteMe': 'present'
                }],
                'actions': [{
                    'type': 'terminate'
                }]
            },
            session_factory=session_factory
        )
        self.assertEqual(1, len(resources))
        workspaceId = resources[0].get('WorkspaceId')
        client = session_factory().client('workspaces')
        call = client.describe_workspaces(WorkspaceIds=[workspaceId])
        self.assertEqual(call['Workspaces'][0]['State'], 'TERMINATING')

    def test_workspaces_image_query_returns_one_resource(self):
        """Test querying Workspaces images returns one