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
        self.assertEqual(len(resources), 1)
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

    def test_workspaces_directory_connection_aliases_false(self):
        session_factory = self.replay_flight_data("test_workspaces_directory_conn_aliases_false")
        p = self.load_policy(
            {
                "name": "workspace-directory-connection-aliases",
                "resource": "workspaces-directory",
                "filters": [{
                    'type': 'connection-aliases',
                    'key': 'ConnectionAliases',
                    'value': 'empty',
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_workspaces_directory_connection_aliases_true(self):
        session_factory = self.replay_flight_data("test_workspaces_directory_conn_aliases_true")
        p = self.load_policy(
            {
                "name": "workspace-directory-connection-aliases",
                "resource": "workspaces-directory",
                "filters": [{
                    'type': 'connection-aliases',
                    'key': 'ConnectionAliases',
                    'value': 'empty',
                    'op': 'ne'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

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

    def test_workspaces_directory_related_directory(self):
        session_factory = self.replay_flight_data('test_workspaces_directory_related_directory')
        p = self.load_policy({
            'name': 'workspace-directory-related-directory',
            'resource': 'aws.workspaces-directory',
            'filters': [{
                'type': 'directory',
                'key': 'RadiusSettings.AuthenticationProtocol',
                'value': 'CHAP'
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n:Directory']['RadiusSettings']['AuthenticationProtocol'],
            'CHAP'
        )


class TestWorkspacesWeb(BaseTest):

    def test_workspaces_web_tag(self):
        session_factory = self.replay_flight_data('test_workspaces_web_tag')
        p = self.load_policy(
            {
                'name': 'test-workspaces-web-tag',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'tag:foo': 'absent',
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('workspaces-web')
        tags = client.list_tags_for_resource(resourceArn=resources[0]["portalArn"])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, [{'Key': 'foo', 'Value': 'bar'}])

    def test_workspaces_web_remove_tag(self):
        session_factory = self.replay_flight_data('test_workspaces_web_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-workspaces-web-remove-tag',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'tag:foo': 'present',
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('workspaces-web')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['portalArn'])['tags']
        self.assertEqual(len(tags), 0)

    def test_workspaces_web_delete(self):
        session_factory = self.replay_flight_data('test_workspaces_web_delete')
        p = self.load_policy(
            {
                'name': 'test-workspaces-web-delete',
                'resource': 'workspaces-web',
                'filters': [{'displayName': 'test'}],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('workspaces-web')
        if self.recording:
            time.sleep(5)
        portals = client.list_portals()['portals']
        self.assertEqual(len(portals), 0)

    def test_workspaces_web_browser_policy(self):
        session_factory = self.replay_flight_data("test_workspaces_web_browser_policy")
        p = self.load_policy(
            {
                "name": "test-browser-policy",
                "resource": "workspaces-web",
                "filters": [
                    {
                        "type": "browser-policy",
                        "key": "chromePolicies.AllowDeletingBrowserHistory.value",
                        "op": "eq",
                        "value": False
                    },
                    {
                        "type": "browser-policy",
                        "key": "chromePolicies.BookmarkBarEnabled.value",
                        "op": "eq",
                        "value": False
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

    # Test for a portal that has disassociated and deleted its browser policy
    # settings.
    def test_workspaces_web_browser_policy_empty(self):
        session_factory = self.replay_flight_data("test_workspaces_web_empty")
        p = self.load_policy(
            {
                "name": "test-browser-policy-empty",
                "resource": "workspaces-web",
                "filters": [{
                    "not": [
                        {
                            "type": "browser-policy",
                            "key": "chromePolicies.AllowDeletingBrowserHistory.value",
                            "op": "eq",
                            "value": False
                        }
                    ]
                }]
            },
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_workspaces_web_subnet(self):
        session_factory = self.replay_flight_data("test_workspaces_web_subnet")
        p = self.load_policy(
            {
                "name": "test-workspaces-web-subnet",
                "resource": "workspaces-web",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "SubnetId",
                        "value": "subnet-068dfbf3f275a6ae8"
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_workspaces_web_user_settings(self):
        session_factory = self.replay_flight_data('test_workspaces_web_user_settings')
        p = self.load_policy(
            {
                'name': 'test-workspaces-web-user-settings',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'type': 'user-settings',
                        'key': 'copyAllowed',
                        "value": 'Disabled'
                    },
                    {
                        'type': 'user-settings',
                        'key': 'downloadAllowed',
                        "value": 'Disabled'
                    },
                    {
                        'type': 'user-settings',
                        'key': 'pasteAllowed',
                        "value": 'Disabled'
                    },
                    {
                        'type': 'user-settings',
                        'key': 'printAllowed',
                        "value": 'Disabled'
                    },
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                'name': 'test-workspaces-web-user-settings',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'type': 'user-settings',
                        'key': 'copyAllowed',
                        "value": 'Enabled'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_workspaces_web_user_access_logging(self):
        session_factory = self.replay_flight_data(
            'test_workspaces_web_user_access_logging'
        )
        p = self.load_policy(
            {
                'name': 'test-workspaces-web-user-access-logging',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'type': 'user-access-logging',
                        'key': 'kinesisStreamArn',
                        "value": 'present'
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                'name': 'test-workspaces-web-user-access-logging',
                'resource': 'workspaces-web',
                'filters': [
                    {
                        'type': 'user-access-logging',
                        'key': 'kinesisStreamArn',
                        "value": 'absent'
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class TestWorkspacesBundleDelete(BaseTest):

    def test_workspaces_bundle_tag(self):
        session_factory = self.replay_flight_data("test_workspaces_bundle_tag")
        client = session_factory().client("workspaces")

        p = self.load_policy({
            'name': 'workspaces-bundle-tag',
            'resource': 'workspaces-bundle',
            'filters': [{'Name': 'test'}],
            'actions': [{
                'type': 'tag',
                'tags': {'test': 'testval'}
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        response = client.describe_tags(ResourceId=resources[0]['BundleId'])
        self.assertIn({'Key': 'test', 'Value': 'testval'}, response.get('TagList', []))

    def test_workspaces_bundle_untag(self):
        session_factory = self.replay_flight_data("test_workspaces_bundle_untag")
        client = session_factory().client("workspaces")

        p = self.load_policy({
            'name': 'workspaces-bundle-untag',
            'resource': 'workspaces-bundle',
            'filters': [{'Name': 'test'}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ['test']
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        response = client.describe_tags(ResourceId=resources[0]['BundleId'])
        self.assertNotIn({'Key': 'test', 'Value': 'testval'}, response.get('TagList', []))

    def test_workspaces_bundle_delete(self):
        session_factory = self.replay_flight_data("test_workspaces_bundle_delete")
        client = session_factory().client("workspaces")

        p = self.load_policy({
            'name': 'workspaces-bundle-delete',
            'resource': 'aws.workspaces-bundle',
            'filters': [{'Name': 'test'}],
            'actions': [{'type': 'delete'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'test')
        if self.recording:
            time.sleep(5)

        response = client.describe_workspace_bundles()['Bundles']
        self.assertFalse(any(b['Name'] == 'test' for b in response))
