# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from dateutil import parser

from .common import BaseTest
from c7n import filters
from c7n.executor import MainThreadExecutor
from c7n.resources.workspaces import Workspace
from c7n.testing import mock_datetime_now
from c7n.utils import annotation


class WorkspacesTest(BaseTest):

    def test_workspaces_query(self):
        session_factory = self.replay_flight_data("test_workspaces_query")
        p = self.load_policy(
            {
                "name": "workspaces-query-test",
                "resource": "workspaces"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_workspaces_tags(self):
        self.patch(Workspace, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_workspaces_query")
        p = self.load_policy(
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
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_connection_status_filter(self):
        session_factory = self.replay_flight_data("test_workspaces_connection_status")
        p = self.load_policy(
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
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('LastKnownUserConnectionTimestamp',
            annotation(resources[0], filters.ANNOTATION_KEY))

    def test_workspaces_kms_filter(self):
        session_factory = self.replay_flight_data('test_workspaces_kms_filter')
        kms = session_factory().client('kms')
        p = self.load_policy(
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
        resources = p.run()
        self.assertTrue(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['VolumeEncryptionKey'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/workspaces')

    def test_workspaces_image_query(self):
        session_factory = self.replay_flight_data("test_workspaces_image_query")
        p = self.load_policy(
            {
                "name": "workspaces-image-query-test",
                "resource": "workspaces-image"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_workspaces_image_tags(self):
        session_factory = self.replay_flight_data('test_workspaces_image_tag')
        new_tag = {'env': 'dev'}
        p = self.load_policy(
            {
                'name': 'workspaces-image-tag',
                'resource': 'workspaces-image',
                'filters': [{
                    'tag:env': 'absent'
                }],
                'actions': [{
                    'type': 'tag',
                    'tags': new_tag
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        imageId = resources[0].get('ImageId')
        workspaces = session_factory().client('workspaces')
        call = workspaces.describe_tags(ResourceId=imageId)
        self.assertEqual({'Key': 'env', 'Value': 'dev'}, call['TagList'][0])

    def test_workspaces_image_permissions(self):
        session_factory = self.replay_flight_data('test_workspaces_image_cross_account')
        p = self.load_policy(
            {
                'name': 'workspaces-image-cross-account',
                'resource': 'workspaces-image',
                'filters': [{
                    'type': 'cross-account'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]['c7n:CrossAccountViolations'], ['XXXXXXXXXXXX'])
