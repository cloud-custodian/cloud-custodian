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

    def test_workspaces_terminate(self):
        session_factory = self.replay_flight_data('test_workspaces_terminate')
        p = self.load_policy(
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
        resources = p.run()
        self.assertEqual(1, len(resources))
        workspaceId = resources[0].get('WorkspaceId')
        client = session_factory().client('workspaces')
        call = client.describe_workspaces(WorkspaceIds=[workspaceId])
        self.assertEqual(call['Workspaces'][0]['State'], 'TERMINATING')

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

    def test_workspaces_image_delete(self):
        session_factory = self.replay_flight_data('test_workspaces_image_delete')
        p = self.load_policy(
            {
                'name': 'workspaces-image-del',
                'resource': 'workspaces-image',
                'filters': [{
                    'tag:DeleteMe': 'present'
                }],
                'actions': [{
                    'type': 'delete'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        imageId = resources[0].get('ImageId')
        client = session_factory().client('workspaces')
        call = client.describe_workspace_images(ImageIds=[imageId])
        self.assertEqual(call['Images'], [])

    def test_workspaces_image_delete_associated_error(self):
        session_factory = self.replay_flight_data('test_workspaces_image_delete_associated_error')
        p = self.load_policy(
            {
                'name': 'workspaces-image-del',
                'resource': 'workspaces-image',
                'filters': [{
                    'tag:DeleteMe': 'present'
                }],
                'actions': [{
                    'type': 'delete'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        imageId = resources[0].get('ImageId')
        client = session_factory().client('workspaces')
        call = client.describe_workspace_images(ImageIds=[imageId])
        self.assertTrue(call['Images'])

    def test_workspaces_directory_deregister(self):
        factory = self.replay_flight_data("test_workspaces_directory_deregister")
        p = self.load_policy(
            {
                "name": "workspace-deregister",
                "resource": "workspaces-directory",
                'filters': [{
                    'tag:Deregister': 'present'
                }],
                'actions': [{
                    'type': 'deregister'
                }]
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(1, len(resources))
        directoryId = resources[0].get('DirectoryId')
        client = factory().client('workspaces')
        if self.recording:
            time.sleep(5)
        call = client.describe_workspace_directories(DirectoryIds=[directoryId])
        self.assertEqual(call['Directories'], [])

    def test_workspaces_directory_deregister_not_supported(self):
        factory = self.replay_flight_data("test_workspaces_directory_deregister_not_supported")
        p = self.load_policy(
            {
                "name": "workspace-deregister",
                "resource": "workspaces-directory",
                'filters': [{
                    'tag:Deregister': 'present'
                }],
                'actions': [{
                    'type': 'deregister'
                }]
            },
            session_factory=factory,
        )
        with self.assertRaises(PolicyExecutionError):
            p.run()

    def test_workspaces_directory_deregister_not_found(self):
        factory = self.replay_flight_data("test_workspaces_directory_deregister_not_found")
        p = self.load_policy(
            {
                "name": "workspace-deregister",
                "resource": "workspaces-directory",
                'filters': [{
                    'tag:Deregister': 'present'
                }],
                'actions': [{
                    'type': 'deregister'
                }]
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(1, len(resources))
        directoryId = resources[0].get('DirectoryId')
        client = factory().client('workspaces')
        call = client.describe_workspace_directories(DirectoryIds=[directoryId])
        self.assertTrue(call['Directories'])

    def test_workspaces_directory_deregister_invalid_state(self):
        factory = self.replay_flight_data("test_workspaces_directory_deregister_invalid_state")
        p = self.load_policy(
            {
                "name": "workspace-deregister",
                "resource": "workspaces-directory",
                'filters': [{
                    'tag:Deregister': 'present'
                }],
                'actions': [{
                    'type': 'deregister'
                }]
            },
            session_factory=factory,
        )

        with patch('c7n.utils.time.sleep', new_callable=time.sleep(0)):
            resources = p.run()
        self.assertEqual(1, len(resources))
        directoryId = resources[0].get('DirectoryId')
        client = factory().client('workspaces')
        call = client.describe_workspace_directories(DirectoryIds=[directoryId])
        self.assertTrue(call['Directories'])

    def test_workspaces_directory_subnet_sg(self):
        factory = self.replay_flight_data("test_workspaces_directory_subnet_sg")
        p = self.load_policy(
            {
                "name": "workspace-directory-sg-subnet",
                "resource": "workspaces-directory",
                "filters": [
                    {'type': 'subnet',
                     'key': 'tag:NetworkLocation',
                     'value': 'Public'},
                    {'type': 'security-group',
                     'key': 'tag:NetworkLocation',
                     'value': 'Private'}],
                'actions': [{
                    'type': 'tag',
                    'key': 'c7n',
                    'value': 'test'
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DirectoryId'], 'd-90675153fc')
        client = factory().client('workspaces')
        tags = client.describe_tags(ResourceId=resources[0]['DirectoryId'])
        self.assertEqual({'Key': 'c7n', 'Value': 'test'}, tags['TagList'][0])

    def test_workspaces_directory_client_properties(self):
        factory = self.replay_flight_data("test_workspaces_directory_client_properties")
        p = self.load_policy(
            {
                "name": "workspace-directory-sg-subnet",
                "resource": "workspaces-directory",
                "filters": [
                    {'type': 'client-properties',
                     'key': 'ReconnectEnabled',
                     'value': 'ENABLED'}],
                'actions': [{
                    'type': 'modify-client-properties',
                    'attributes': {
                        'ClientProperties': {'ReconnectEnabled': 'DISABLED'}
                    }
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DirectoryId'], 'd-90675153fc')
        client = factory().client('workspaces')
        cp = client.describe_client_properties(ResourceIds=['d-90675153fc'])
        self.assertEqual({'ReconnectEnabled': 'DISABLED'}, cp.get(
            'ClientPropertiesList')[0].get('ClientProperties'))
