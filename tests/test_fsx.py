# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time
from dateutil.parser import parse as date_parse

import c7n.resources.fsx
import c7n.resources.directory
from c7n.testing import mock_datetime_now
from .common import BaseTest
import c7n.filters.backup
from unittest.mock import MagicMock, patch


class TestFSx(BaseTest):
    def test_fsx_resource(self):
        session_factory = self.replay_flight_data('test_fsx_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))

    def test_fsx_tag_resource(self):
        session_factory = self.replay_flight_data('test_fsx_tag_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'key': 'test',
                        'value': 'test-value'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertTrue([t for t in tags['Tags'] if t['Key'] == 'test'])

    def test_fsx_remove_tag_resource(self):
        session_factory = self.replay_flight_data('test_fsx_remove_tag_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': [
                            'maid_status',
                            'test'
                        ],
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertFalse([t for t in tags['Tags'] if t['Key'] != 'Name'])

    def test_fsx_mark_for_op_resource(self):
        session_factory = self.replay_flight_data('test_fsx_mark_for_op_resource')
        p = self.load_policy(
            {
                'name': 'test-fsx',
                'resource': 'fsx',
                'filters': [
                    {
                        'tag:Name': 'test'
                    }
                ],
                'actions': [
                    {
                        'type': 'mark-for-op',
                        'op': 'tag'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources))
        client = session_factory().client('fsx')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['ResourceARN'])

        self.assertTrue([t for t in tags['Tags'] if t['Key'] == 'maid_status'])

    def test_fsx_update_configuration(self):
        session_factory = self.replay_flight_data('test_fsx_update_configuration')
        p = self.load_policy(
            {
                'name': 'test-update-fsx-configuration',
                'resource': 'fsx',
                'filters': [
                    {
                        'WindowsConfiguration.AutomaticBackupRetentionDays': 1
                    }
                ],
                'actions': [
                    {
                        'type': 'update',
                        'WindowsConfiguration': {
                            'AutomaticBackupRetentionDays': 3
                        }
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        new_resources = client.describe_file_systems()['FileSystems']
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            new_resources[0]['FileSystemId'],
            resources[0]['FileSystemId']
        )
        self.assertEqual(
            new_resources[0]['WindowsConfiguration']['AutomaticBackupRetentionDays'], 3)

    def test_fsx_create_bad_backup(self):
        session_factory = self.replay_flight_data('test_fsx_create_backup_with_errors')
        p = self.load_policy(
            {
                'name': 'test-update-fsx-configuration',
                'resource': 'fsx',
                'filters': [
                    {
                        'FileSystemId': 'fs-0bc98cbfb6b356896'
                    }
                ],
                'actions': [
                    {
                        'type': 'backup',
                        'tags': {
                            'test-tag': 'backup-tag'
                        }
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

        client = session_factory().client('fsx')

        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-0bc98cbfb6b356896']
                },
                {
                    'Name': 'backup-type',
                    'Values': ['USER_INITIATED']
                }
            ]
        )
        self.assertEqual(len(backups['Backups']), 0)

    def test_fsx_create_backup(self):
        session_factory = self.replay_flight_data('test_fsx_create_backup')
        p = self.load_policy(
            {
                'name': 'test-update-fsx-configuration',
                'resource': 'fsx',
                'filters': [
                    {
                        'FileSystemId': 'fs-002ccbccdcf032728'
                    }
                ],
                'actions': [
                    {
                        'type': 'backup',
                        'copy-tags': True,
                        'tags': {
                            'test-tag': 'backup-tag'
                        }
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)

        client = session_factory().client('fsx')

        if self.recording:
            time.sleep(500)

        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                },
                {
                    'Name': 'backup-type',
                    'Values': ['USER_INITIATED']
                }
            ]
        )

        self.assertEqual(len(backups['Backups']), 1)

        expected_tags = resources[0]['Tags']

        expected_tags.append({'Key': 'test-tag', 'Value': 'backup-tag'})
        expected_tag_map = {t['Key']: t['Value'] for t in expected_tags}
        final_tag_map = {t['Key']: t['Value'] for t in backups['Backups'][0]['Tags']}

        self.assertEqual(expected_tag_map, final_tag_map)

    def test_fsx_create_backup_without_copy_tags(self):
        session_factory = self.replay_flight_data('test_fsx_create_backup_without_copy_tags')
        p = self.load_policy(
            {
                'name': 'test-update-fsx-configuration',
                'resource': 'fsx',
                'filters': [
                    {
                        'FileSystemId': 'fs-002ccbccdcf032728'
                    }
                ],
                'actions': [
                    {
                        'type': 'backup',
                        'copy-tags': False,
                        'tags': {
                            'test-tag': 'backup-tag'
                        }
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(500)

        client = session_factory().client('fsx')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                },
                {
                    'Name': 'backup-type',
                    'Values': ['USER_INITIATED']
                }
            ]
        )
        self.assertEqual(len(backups['Backups']), 1)
        expected_tags = [{'Key': 'test-tag', 'Value': 'backup-tag'}]
        self.assertEqual(expected_tags, backups['Backups'][0]['Tags'])

    def test_fsx_delete_file_system_skip_snapshot_windows(self):
        session_factory = self.replay_flight_data('test_fsx_delete_file_system_skip_snapshot')
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [fs[0]['FileSystemId']]
                },
                {
                    'Name': 'backup-type',
                    'Values': ['USER_INITIATED']
                }
            ]
        )['Backups']
        self.assertEqual(len(backups), 0)

    def test_fsx_delete_file_system_windows(self):
        session_factory = self.replay_flight_data('test_fsx_delete_file_system')
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'WINDOWS'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'tags': {
                            'DeletedBy': 'CloudCustodian'
                        },
                        'skip-snapshot': False
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': [fs[0]['FileSystemId']]
                },
                {
                    'Name': 'backup-type',
                    'Values': ['USER_INITIATED']
                }
            ]
        )['Backups']
        self.assertEqual(len(backups), 1)

    def test_fsx_delete_file_system_ontap(self):
        # Delete fsx resource with volumes and svms.
        # Ontap does not create snapshot backups on deletion even if
        # skip-snapshot is set to False.
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_ontap', region="us-west-2")
        #  Adjust retry settings for recording playback speed.
        if not self.recording:
            retry_delay = 1
            retry_max_attempts = 2
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'ONTAP'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'force': True,
                        'retry-delay': retry_delay,
                        'retry-max-attempts': retry_max_attempts,
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')

    def test_fsx_delete_file_system_ontap_mock_skip_dependencies(self):
        #  Skip over dependencies that are already pending deletion.
        factory = self.replay_flight_data("test_fsx_delete_file_system_ontap")

        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            # Mock describe_file_systems to return AVAILABLE ONTAP fs
            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "ONTAP",
                    }
                ]
            }

            # Mock describe_volumes to return volumes in DELETING state
            mock_client.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-12345678",
                        "Lifecycle": "DELETING",
                    }
                ]
            }

            # Mock describe_storage_virtual_machines to return in DELETING state
            mock_client.describe_storage_virtual_machines.return_value = {
                "StorageVirtualMachines": [
                    {
                        "StorageVirtualMachineId": "svm-12345678",
                        "Lifecycle": "DELETING",
                    }
                ]
            }

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "ONTAP",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.describe_storage_virtual_machines.assert_called_once()
            mock_client.describe_volumes.assert_called_once()
            mock_client.delete_storage_virtual_machine.assert_not_called()
            mock_client.delete_volume.assert_not_called()

    def test_fsx_delete_file_system_ontap_mock_actions_called(self):
        factory = self.replay_flight_data("test_fsx_delete_file_system_ontap")
        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            # Mock describe_file_systems to return AVAILABLE ONTAP fs
            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "ONTAP",
                    }
                ]
            }

            # Mock describe_volumes to return volumes in AVAILABLE state
            mock_client.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-12345678",
                        "Lifecycle": "AVAILABLE",
                    }
                ]
            }

            # Mock describe_storage_virtual_machines to return in AVAILABLE state
            mock_client.describe_storage_virtual_machines.return_value = {
                "StorageVirtualMachines": [
                    {
                        "StorageVirtualMachineId": "svm-12345678",
                        "Lifecycle": "AVAILABLE",
                    }
                ]
            }

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "ONTAP",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.describe_storage_virtual_machines.assert_called_once()
            mock_client.describe_volumes.assert_called_once()
            mock_client.delete_storage_virtual_machine.assert_called_once()
            mock_client.delete_volume.assert_called_once()
            mock_client.delete_file_system.assert_called_once()

    def test_fsx_delete_file_system_ontap_mock_exception_svm_error(self):
        # Example of InternalServerError handling during dependency deletion.
        factory = self.replay_flight_data("test_fsx_delete_file_system_ontap")
        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            # Mock describe_file_systems to return AVAILABLE ONTAP fs
            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "ONTAP",
                    }
                ]
            }

            # Mock describe_storage_virtual_machines to return in AVAILABLE state
            mock_client.describe_storage_virtual_machines.return_value = {
                "StorageVirtualMachines": [
                    {
                        "StorageVirtualMachineId": "svm-12345678",
                        "Lifecycle": "AVAILABLE",
                    }
                ]
            }

            # Mock delete_storage_virtual_machine to raise InternalServerError
            mock_client.delete_storage_virtual_machine.side_effect = (
                mock_client.exceptions.InternalServerError(
                    {"Error": {"Code": "InternalServerError"}},
                    "DeleteStorageVirtualMachine")
            )

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "ONTAP",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.delete_storage_virtual_machine.assert_called_once()
            assert mock_client.delete_storage_virtual_machine.side_effect

    def test_fsx_delete_file_system_ontap_mock_exception_volume_error(self):
        # Example of InternalServerError handling during volume deletion.
        factory = self.replay_flight_data("test_fsx_delete_file_system_ontap")
        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            # Mock describe_file_systems to return AVAILABLE ONTAP fs
            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "ONTAP",
                    }
                ]
            }

            # Mock describe_volumes to return volumes in AVAILABLE state
            mock_client.describe_volumes.return_value = {
                "Volumes": [
                    {
                        "VolumeId": "vol-12345678",
                        "Lifecycle": "AVAILABLE",
                    }
                ]
            }

            # Mock delete_volume to raise InternalServerError
            mock_client.delete_volume.side_effect = (
                mock_client.exceptions.InternalServerError(
                    {"Error": {"Code": "InternalServerError"}},
                    "DeleteVolume")
            )

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "ONTAP",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.delete_volume.assert_called_once()
            assert mock_client.delete_volume.side_effect

    def test_fsx_delete_file_system_openzfs(self):
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_openzfs',
            region="us-west-2")
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'OPENZFS'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')

    def test_fsx_delete_file_system_openzfs_mock_skip(self):
        # Skip over s3 access point already pending deletion.
        factory = self.replay_flight_data("test_fsx_delete_file_system_openzfs")
        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            # Mock describe_file_systems to return AVAILABLE OPENZFS fs
            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "OPENZFS",
                    }
                ]
            }

            # Mock describe_s3_access_point_attachments to return in DELETING state
            mock_client.describe_s3_access_point_attachments.return_value = {
                "S3AccessPointAttachments": [
                    {
                        "S3AccessPoint": {
                            "ResourceARN": "arn:aws:s3:accesspoint:example"
                        },
                        "Lifecycle": "DELETING",
                        "Name": "example-access-point",
                    }
                ]
            }

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "OPENZFS",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.describe_s3_access_point_attachments.assert_called_once()
            mock_client.detach_and_delete_s3_access_point.assert_not_called()

    def test_fsx_delete_file_system_openzfs_mock(self):
        # Make sure s3 access point and file system deletion methods are called.
        factory = self.replay_flight_data("test_fsx_delete_file_system_openzfs")
        with patch("c7n.resources.fsx.local_session", autospec=True) as mock_local_session:
            mock_client = MagicMock()
            mock_local_session.return_value.client.return_value = mock_client

            mock_client.describe_file_systems.return_value = {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Lifecycle": "AVAILABLE",
                        "FileSystemType": "OPENZFS",
                    }
                ]
            }

            mock_client.describe_s3_access_point_attachments.return_value = {
                "S3AccessPointAttachments": [
                    {
                        "S3AccessPoint": {
                            "ResourceARN": "arn:aws:s3:accesspoint:example"
                        },
                        "Lifecycle": "AVAILABLE",
                        "Name": "example-access-point",
                    }
                ]
            }

            p = self.load_policy(
                {
                    "name": "fsx-delete-file-system",
                    "resource": "fsx",
                    "filters": [
                        {
                            "type": "value",
                            "key": "Lifecycle",
                            "value": "AVAILABLE",
                        },
                        {
                            "type": "value",
                            "key": "FileSystemType",
                            "value": "OPENZFS",
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete",
                            "force": True,
                            "skip-snapshot": True,
                        }
                    ],
                },
                session_factory=factory
            )
            resources = p.run()
            self.assertEqual(len(resources), 1)
            mock_client.describe_s3_access_point_attachments.assert_called_once()
            mock_client.detach_and_delete_s3_access_point.assert_called_once()
            mock_client.delete_file_system.assert_called_once()

    def test_fsx_delete_file_system_openzfs_force(self):
        # Against a resource with child volumes and s3 access point.
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_openzfs_force',
            region="us-west-2")

        # Adjust retry settings for recording playback speed.
        if not self.recording:
            retry_delay = 1
            retry_max_attempts = 5
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'OPENZFS'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'force': True,
                        'retry-delay': retry_delay,
                        'retry-max-attempts': retry_max_attempts,
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')

    def test_fsx_delete_file_system_lustre(self):
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_lustre', region="us-west-2")

        if not self.recording:
            retry_delay = 1
            retry_max_attempts = 2

        # Even if skip-snapshot is False, resources with Scratch deployments
        # do not support final backups on deletion. The force parameter will
        # attempt to delete even though a final backup cannot be created.
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'LUSTRE'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'force': True,
                        'retry-delay': retry_delay,
                        'retry-max-attempts': retry_max_attempts,
                        'skip-snapshot': False
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        fs = client.describe_file_systems(
            FileSystemIds=[resources[0]['FileSystemId']])['FileSystems']
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]['Lifecycle'], 'DELETING')

    def test_fsx_delete_file_system_with_error(self):
        session_factory = self.replay_flight_data('test_fsx_delete_file_system_with_error')
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'CREATING'
                    }
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            },
            session_factory=session_factory
        )
        # error because you cannot delete a creating fsx resource.
        with self.assertRaises(Exception):
            p.run()

    def test_fsx_delete_file_system_ontap_error(self):
        # Delete fsx resource with volumes and svms without force flag
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_ontap_error', region="us-west-2")
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'ONTAP'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'retry-delay': 1,
                        'retry-max-attempts': 3,
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        with self.assertRaises(Exception):
            p.run()

    def test_fsx_delete_file_system_openzfs_error(self):
        # Against a resource with child volumes and s3 access point.
        # No force flag set should raise error.
        session_factory = self.replay_flight_data(
            'test_fsx_delete_file_system_openzfs_error',
            region="us-west-2")
        p = self.load_policy(
            {
                'name': 'fsx-delete-file-system',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'Lifecycle',
                        'value': 'AVAILABLE'
                    },
                    {
                        'type': 'value',
                        'key': 'FileSystemType',
                        'value': 'OPENZFS'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'force': True,
                        'retry-delay': 1,
                        'retry-max-attempts': 3,
                        'skip-snapshot': True
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        with self.assertRaises(Exception):
            p.run()

    def test_fsx_arn_in_event(self):
        session_factory = self.replay_flight_data('test_fsx_resource')
        p = self.load_policy({'name': 'test-fsx', 'resource': 'fsx'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(
            ["arn:aws:fsx:us-east-1:644160558196:file-system/fs-0bc98cbfb6b356896"])
        self.assertEqual(len(resources), 1)

    def test_fsx_backup_count_filter(self):
        session_factory = self.replay_flight_data("test_fsx_backup_count_filter")
        p = self.load_policy(
            {
                "name": "fsx-backup-count-filter",
                "resource": "fsx",
                "filters": [{"type": "consecutive-backups", "days": 2}],
            },
            config={'region': 'us-west-2'},
            session_factory=session_factory,
        )
        with mock_datetime_now(date_parse("2022-07-04"), c7n.resources.fsx):
            resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_fsx_igw_subnet(self):
        factory = self.replay_flight_data('test_fsx_public_subnet')
        p = self.load_policy({
            'name': 'fsx-public',
            'resource': 'fsx',
            'filters': [
                {'type': 'subnet',
                 'key': 'SubnetId',
                 'value': 'present',
                 'igw': True}
            ]}, config={'region': 'us-west-2'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_fsx_consecutive_aws_backups_count_filter(self):
        session_factory = self.replay_flight_data("test_fsx_consecutive_aws_backups_count_filter")
        p = self.load_policy(
            {
                "name": "fsx_consecutive_aws_backups_count_filter",
                "resource": "fsx",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 2,
                        "period": "days",
                        "status": "COMPLETED"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(date_parse("2022-09-09T00:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_fsx_volumes_filter(self):
        session_factory = self.replay_flight_data("test_fsx_volumes_filter")
        p = self.load_policy({
            "name": "fsx_volumes_filter",
            "resource": "aws.fsx",
            "filters": [{
                "type": "volume",
                "attrs": []
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:Volumes']), 2)

    def test_fsx_vpc_filter(self):
        session_factory = self.replay_flight_data("test_fsx_vpc_filter")
        p = self.load_policy({
            "name": "fsx_vpc_filter",
            "resource": "aws.fsx",
            "filters": [{
                "type": "vpc",
                "key": "IsDefault",
                "value": True
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-vpcs']), 1)

    def test_fsx_security_group_filter(self):
        session_factory = self.replay_flight_data("test_fsx_network_location_sg")
        p = self.load_policy({
            "name": "fsx_security_group_filter",
            "resource": "aws.fsx",
            "filters": [{
                "type": "security-group",
                "key": "tag:Env",
                "value": "Staging"
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-0bc98cbfb6b356896")
        self.assertEqual(
            resources[0]["c7n:matched-security-groups"],
            ["sg-0stag00000000000b"])

    def test_fsx_security_group_filter_multiple_enis(self):
        # an ontap file system carries an eni per ha pair, both of which
        # have to resolve back to the same file system.
        session_factory = self.replay_flight_data("test_fsx_network_location_sg")
        p = self.load_policy({
            "name": "fsx_security_group_filter_multi_eni",
            "resource": "aws.fsx",
            "filters": [{
                "type": "security-group",
                "key": "GroupName",
                "value": "fsx-prod"
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-0e3e2a9e1f5ff7a13")
        # both of the file system's enis carry the same group, and it
        # resolves once rather than twice
        self.assertEqual(
            resources[0]["c7n:matched-security-groups"], ["sg-0prod00000000000a"])

    def test_fsx_network_location_sg_mismatch(self):
        session_factory = self.replay_flight_data("test_fsx_network_location_sg")
        p = self.load_policy({
            "name": "fsx_network_location_sg",
            "resource": "aws.fsx",
            "filters": [{
                "type": "network-location",
                "compare": ["resource", "security-group"],
                "key": "tag:Env"
            }]
        }, session_factory=session_factory)
        resources = p.run()
        # the ontap file system's tag matches its security group, the
        # windows one (Dev) does not match its group (Staging).
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["FileSystemId"], "fs-0bc98cbfb6b356896")
        self.assertEqual(
            resources[0]["c7n:NetworkLocation"],
            [{"reason": "ResourceLocationMismatch",
              "resource": "Dev",
              "security-groups": {"sg-0stag00000000000b": "Staging"}},
             {"reason": "SecurityGroupMismatch",
              "resource": "Dev",
              "security-groups": {"sg-0stag00000000000b": "Staging"}}])

    def test_fsx_network_location_permissions(self):
        p = self.load_policy({
            "name": "fsx_network_location_permissions",
            "resource": "aws.fsx",
            "filters": [{
                "type": "network-location",
                "compare": ["resource", "security-group"],
                "key": "tag:Env"
            }]
        })
        # security groups come off the file system's enis, which the base
        # network-location filter doesn't account for.
        self.assertIn("ec2:DescribeNetworkInterfaces", p.get_permissions())

    def test_fsx_metrics_filter(self):
        session_factory = self.replay_flight_data('test_fsx_metrics_filter')
        p = self.load_policy(
            {
                'name': 'test-fsx-metrics',
                'resource': 'fsx',
                'filters': [
                    {
                        'type': 'metrics',
                        'name': 'CPUUtilization',
                        'value': 0,
                        'op': 'gt',
                        'days': 7,
                        'statistics': 'Average'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)


class TestFSxVolume(BaseTest):
    def test_fsx_volume_query(self):
        session_factory = self.replay_flight_data('test_fsx_volume_query')
        p = self.load_policy(
            {
                "name": "fsx_volume_query",
                "resource": "aws.fsx-volume",
                "filters": [{
                    "type": "value",
                    "key": "Lifecycle",
                    "value": "AVAILABLE"
                }]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestFSxBackup(BaseTest):
    def test_fsx_backup_delete(self):
        session_factory = self.replay_flight_data('test_fsx_backup_delete')
        backup_id = 'backup-0d1fb25003287b260'
        p = self.load_policy(
            {
                'name': 'fsx-backup-resource',
                'resource': 'fsx-backup',
                'filters': [
                    {'BackupId': backup_id}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = session_factory().client('fsx')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                }
            ]
        )['Backups']
        results = [b for b in backups if b['BackupId'] == backup_id]
        self.assertFalse(results)

    def test_fsx_backup_tag(self):
        session_factory = self.replay_flight_data('test_fsx_backup_tag')
        backup_id = 'backup-0b644cd380298f720'
        p = self.load_policy(
            {
                'name': 'fsx-backup-resource-tag',
                'resource': 'fsx-backup',
                'filters': [
                    {'BackupId': backup_id},
                    {'Tags': []}
                ],
                'actions': [
                    {'type': 'tag', 'tags': {'tag-test': 'tag-test'}}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fsx')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                }
            ]
        )['Backups']
        tags = None
        for b in backups:
            if b['BackupId'] == backup_id:
                self.assertEqual(len(b['Tags']), 1)
                tags = b['Tags']
        self.assertTrue(tags)
        self.assertEqual(tags[0]['Key'], 'tag-test')
        self.assertEqual(tags[0]['Value'], 'tag-test')

    def test_fsx_backup_mark_for_op(self):
        session_factory = self.replay_flight_data('test_fsx_backup_mark_for_op')
        backup_id = 'backup-09d3dfca849cfc629'
        p = self.load_policy(
            {
                'name': 'fsx-backup-resource-mark-for-op',
                'resource': 'fsx-backup',
                'filters': [
                    {'BackupId': backup_id},
                    {'Tags': []}
                ],
                'actions': [
                    {'type': 'mark-for-op', 'op': 'delete'}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('fsx')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                }
            ]
        )['Backups']
        tags = None
        for b in backups:
            if b['BackupId'] == backup_id:
                self.assertEqual(len(b['Tags']), 1)
                tags = [t for t in b['Tags'] if t['Key'] == 'maid_status']
        self.assertTrue(tags)

    def test_fsx_backup_remove_tag(self):
        session_factory = self.replay_flight_data('test_fsx_backup_remove_tag')
        backup_id = 'backup-05c81253149962783'
        p = self.load_policy(
            {
                'name': 'fsx-backup-resource-remove-tag',
                'resource': 'fsx-backup',
                'filters': [
                    {'BackupId': backup_id},
                    {'tag:test-tag': 'backup-tag'},
                ],
                'actions': [
                    {'type': 'remove-tag', 'tags': ['test-tag']}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('fsx')
        backups = client.describe_backups(
            Filters=[
                {
                    'Name': 'file-system-id',
                    'Values': ['fs-002ccbccdcf032728']
                }
            ]
        )['Backups']
        tags = [1]
        for b in backups:
            if b['BackupId'] == backup_id:
                if len(b['Tags']) == 0:
                    tags = b['Tags']
        self.assertEqual(len(tags), 0)

    def test_kms_key_filter(self):
        session_factory = self.replay_flight_data("test_fsx_kms_key_filter")
        p = self.load_policy(
            {
                "name": "fsx-kms-key-filters",
                "resource": "fsx",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/fsx)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-kms-key']), 1)

    def test_kms_key_filter_fsx_backup(self):
        session_factory = self.replay_flight_data("test_kms_key_filter_fsx_backup")
        p = self.load_policy(
            {
                "name": "kms_key_filter_fsx_backup",
                "resource": "fsx-backup",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/aws/fsx)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        for r in resources:
            self.assertEqual(len(r['c7n:matched-kms-key']), 1)


class TestFSxStorageVirtualMachine(BaseTest):

    def test_svm_query(self):
        session_factory = self.replay_flight_data("test_fsx_svm_managed_ad")
        p = self.load_policy({
            "name": "fsx_svm_query",
            "resource": "aws.fsx-storage-virtual-machine",
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(
            sorted(r["StorageVirtualMachineId"] for r in resources),
            ["svm-05b1f4f80089ba22d", "svm-097e3d446a223c732"])

    def test_svm_not_joined_to_managed_ad(self):
        session_factory = self.replay_flight_data("test_fsx_svm_managed_ad")
        p = self.load_policy({
            "name": "fsx-ontap-svm-must-use-managed-ad",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{
                "type": "active-directory",
                "key": "Type",
                "value": ["MicrosoftAD", "SharedMicrosoftAD"],
                "op": "not-in"}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["StorageVirtualMachineId"], "svm-05b1f4f80089ba22d")
        # nothing resolved, so no directory is annotated and the value filter
        # matches rather than clearing it
        self.assertEqual(resources[0]["c7n:ActiveDirectory"], {})
        self.assertEqual(
            resources[0]["c7n:ActiveDirectoryResolution"],
            {"reason": "NoActiveDirectory"})

    def test_svm_joined_to_managed_ad_annotates_the_directory(self):
        session_factory = self.replay_flight_data("test_fsx_svm_managed_ad")
        p = self.load_policy({
            "name": "fsx_svm_managed_ad",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{
                "type": "active-directory",
                "key": "Type",
                "value": ["MicrosoftAD", "SharedMicrosoftAD"],
                "op": "in"}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        r = resources[0]
        self.assertEqual(r["StorageVirtualMachineId"], "svm-097e3d446a223c732")
        # fsx reports CORP.C7NTEST.COM, directory service corp.c7ntest.com
        self.assertEqual(
            r["ActiveDirectoryConfiguration"][
                "SelfManagedActiveDirectoryConfiguration"]["DomainName"],
            "CORP.C7NTEST.COM")
        # the annotation is the directory as directory service returns it
        self.assertEqual(r["c7n:ActiveDirectory"]["DirectoryId"], "d-90667bfee0")
        self.assertEqual(r["c7n:ActiveDirectory"]["Type"], "MicrosoftAD")
        self.assertEqual(
            r["c7n:ActiveDirectoryResolution"]["matched-on"], "dns-ips,domain-name")

    def test_svm_permissions(self):
        p = self.load_policy({
            "name": "fsx_svm_permissions",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{"type": "active-directory", "key": "Type", "value": "MicrosoftAD"}],
        })
        perms = p.get_permissions()
        self.assertIn("ds:DescribeDirectories", perms)
        self.assertIn("fsx:DescribeStorageVirtualMachines", perms)


class TestFSxActiveDirectoryResolution(BaseTest):
    """Resolution cases that can't be provoked against a live account."""

    def filter(self):
        return c7n.resources.fsx.SvmActiveDirectoryFilter(
            {"type": "active-directory", "key": "Type", "value": "MicrosoftAD"}, None)

    def directories(self):
        return [{"DirectoryId": "d-managed", "Name": "corp.example.com",
                 "Type": "MicrosoftAD", "DnsIpAddrs": ["10.0.0.10", "10.0.0.11"]}]

    def svm(self, **ad):
        return {"Subtype": "DEFAULT", "Lifecycle": "CREATED",
                "ActiveDirectoryConfiguration": {
                    "SelfManagedActiveDirectoryConfiguration": ad}}

    def test_dns_ip_match_resolves(self):
        directory, resolution = self.filter().resolve(
            self.svm(DomainName="CORP.EXAMPLE.COM", DnsIps=["10.0.0.10"]),
            self.directories())
        self.assertEqual(directory["DirectoryId"], "d-managed")
        self.assertEqual(resolution["matched-on"], "dns-ips,domain-name")

    def test_domain_name_alone_does_not_resolve(self):
        # an on premises domain of the same name resolves by name too, so a
        # name match on its own can't establish which controllers are in use.
        directory, resolution = self.filter().resolve(
            self.svm(DomainName="CORP.EXAMPLE.COM", DnsIps=["192.168.50.5"]),
            self.directories())
        self.assertIsNone(directory)
        self.assertEqual(resolution["reason"], "DomainNameOnlyMatch")
        self.assertEqual(resolution["DirectoryId"], "d-managed")

    def test_duplicate_domain_names_resolve_deterministically(self):
        svm = self.svm(DomainName="CORP.EXAMPLE.COM", DnsIps=["192.168.50.5"])
        directories = [
            {"DirectoryId": "d-1", "Name": "corp.example.com",
             "Type": "MicrosoftAD", "DnsIpAddrs": ["10.0.0.1"]},
            {"DirectoryId": "d-2", "Name": "corp.example.com",
             "Type": "SimpleAD", "DnsIpAddrs": ["10.0.0.2"]}]
        self.assertEqual(
            self.filter().resolve(svm, directories)[1]["DirectoryId"], "d-1")
        self.assertEqual(
            self.filter().resolve(svm, list(reversed(directories)))[1]["DirectoryId"],
            "d-2")

    def test_shared_managed_directory(self):
        # a directory shared from another account reports the owning account's
        # domain controllers. unverified against live aws.
        directories = [{"DirectoryId": "d-shared", "Name": "corp.example.com",
                        "Type": "SharedMicrosoftAD", "DnsIpAddrs": [],
                        "OwnerDirectoryDescription": {
                            "DirectoryId": "d-owner", "AccountId": "111111111111",
                            "DnsIpAddrs": ["10.9.0.10"]}}]
        directory, _ = self.filter().resolve(
            self.svm(DomainName="CORP.EXAMPLE.COM", DnsIps=["10.9.0.10"]), directories)
        self.assertEqual(directory["Type"], "SharedMicrosoftAD")

    def test_unresolved_directory(self):
        directory, resolution = self.filter().resolve(
            self.svm(DomainName="OTHER.EXAMPLE.COM", DnsIps=["192.168.1.1"]),
            self.directories())
        self.assertIsNone(directory)
        self.assertEqual(resolution["reason"], "UnresolvedDirectory")

    def test_replication_targets_and_transient_svms_out_of_scope(self):
        f = self.filter()
        self.assertFalse(f.in_scope({"Subtype": "DP_DESTINATION", "Lifecycle": "CREATED"}))
        self.assertFalse(f.in_scope({"Subtype": "SYNC_SOURCE", "Lifecycle": "CREATED"}))
        self.assertFalse(f.in_scope({"Subtype": "DEFAULT", "Lifecycle": "CREATING"}))
        self.assertTrue(f.in_scope({"Subtype": "DEFAULT", "Lifecycle": "CREATED"}))
        # a misconfigured svm stays in scope, a policy pairs the directory
        # check with its lifecycle
        self.assertTrue(f.in_scope({"Subtype": "DEFAULT", "Lifecycle": "MISCONFIGURED"}))

    def forwarder_svm(self):
        # joined to the managed ad, but pointed at a resolver endpoint rather
        # than at the domain controllers themselves
        return dict(self.svm(DomainName="CORP.EXAMPLE.COM", DnsIps=["10.0.0.2"]),
                    FileSystemId="fs-1")

    def vpc_directories(self):
        return [dict(self.directories()[0], VpcSettings={"VpcId": "vpc-1"})]

    def test_resolve_on_defaults_to_dns_ips(self):
        f = self.filter()
        directory, resolution = f.resolve(
            self.forwarder_svm(), self.vpc_directories(), {"fs-1": "vpc-1"})
        self.assertIsNone(directory)
        self.assertEqual(resolution["reason"], "DomainNameOnlyMatch")

    def test_resolve_on_same_vpc(self):
        f = c7n.resources.fsx.SvmActiveDirectoryFilter(
            {"type": "active-directory", "key": "Type", "value": "MicrosoftAD",
             "resolve-on": "same-vpc"}, None)
        directory, resolution = f.resolve(
            self.forwarder_svm(), self.vpc_directories(), {"fs-1": "vpc-1"})
        self.assertEqual(directory["DirectoryId"], "d-managed")
        self.assertEqual(resolution["matched-on"], "domain-name,same-vpc")

    def test_resolve_on_same_vpc_rejects_a_different_vpc(self):
        # an on premises domain of the same name reached from another vpc
        # still doesn't resolve
        f = c7n.resources.fsx.SvmActiveDirectoryFilter(
            {"type": "active-directory", "key": "Type", "value": "MicrosoftAD",
             "resolve-on": "same-vpc"}, None)
        directory, resolution = f.resolve(
            self.forwarder_svm(), self.vpc_directories(), {"fs-1": "vpc-2"})
        self.assertIsNone(directory)
        self.assertEqual(resolution["reason"], "DomainNameOnlyMatch")

    def test_resolve_on_same_vpc_is_order_independent(self):
        # several directories can carry the same domain name, the one in the
        # file system's vpc has to be found wherever the api returns it
        f = c7n.resources.fsx.SvmActiveDirectoryFilter(
            {"type": "active-directory", "key": "Type", "value": "MicrosoftAD",
             "resolve-on": "same-vpc"}, None)
        directories = [
            {"DirectoryId": "d-other", "Name": "corp.example.com",
             "Type": "MicrosoftAD", "DnsIpAddrs": ["10.5.0.1"],
             "VpcSettings": {"VpcId": "vpc-other"}},
            {"DirectoryId": "d-same", "Name": "corp.example.com",
             "Type": "MicrosoftAD", "DnsIpAddrs": ["10.0.0.10"],
             "VpcSettings": {"VpcId": "vpc-1"}}]
        for order in (directories, list(reversed(directories))):
            directory, resolution = f.resolve(
                self.forwarder_svm(), order, {"fs-1": "vpc-1"})
            self.assertEqual(directory["DirectoryId"], "d-same")
            self.assertEqual(resolution["matched-on"], "domain-name,same-vpc")

    def test_resolve_on_domain_name(self):
        f = c7n.resources.fsx.SvmActiveDirectoryFilter(
            {"type": "active-directory", "key": "Type", "value": "MicrosoftAD",
             "resolve-on": "domain-name"}, None)
        directory, resolution = f.resolve(
            self.forwarder_svm(), self.vpc_directories(), None)
        self.assertEqual(directory["DirectoryId"], "d-managed")
        self.assertEqual(resolution["matched-on"], "domain-name")

    def test_resolve_on_same_vpc_declares_the_extra_permission(self):
        p = self.load_policy({
            "name": "fsx_svm_same_vpc",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{"type": "active-directory", "key": "Type",
                         "value": "MicrosoftAD", "resolve-on": "same-vpc"}]})
        self.assertIn("fsx:DescribeFileSystems", p.get_permissions())


class TestFSxDirectory(BaseTest):

    def test_windows_directory_no_longer_exists(self):
        # ActiveDirectoryId outlives the directory it names, so relating it
        # catches an id left behind by a deleted directory.
        session_factory = self.replay_flight_data("test_fsx_active_directory")
        p = self.load_policy({
            "name": "fsx-windows-must-use-managed-ad",
            "resource": "aws.fsx",
            "filters": [
                {"FileSystemType": "WINDOWS"},
                {"or": [
                    # a related resource that can't be resolved is only a
                    # match for value: absent, so the deleted directory has
                    # to be asked for separately
                    {"type": "directory", "key": "DirectoryId", "value": "absent"},
                    {"type": "directory", "key": "Type",
                     "value": ["MicrosoftAD", "SharedMicrosoftAD"],
                     "op": "not-in"}]}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(
            [r["FileSystemId"] for r in resources], ["fs-0bc98cbfb6b356896"])

    def test_ontap_without_storage_virtual_machine(self):
        session_factory = self.replay_flight_data("test_fsx_active_directory")
        p = self.load_policy({
            "name": "fsx-ontap-without-svm",
            "resource": "aws.fsx",
            "filters": [
                {"FileSystemType": "ONTAP"},
                {"type": "svm", "count": 0}],
        }, session_factory=session_factory)
        resources = p.run()
        # the recorded ontap file system has two svms
        self.assertEqual(resources, [])

    def test_windows_self_managed_join_is_flagged(self):
        # a self managed join reports no ActiveDirectoryId at all, so the
        # related resource filter has no id to resolve and can't match it
        directories = [{"DirectoryId": "d-managed", "Name": "corp.example.com",
                        "Type": "MicrosoftAD", "DnsIpAddrs": ["10.0.0.10"]}]
        self.patch(c7n.resources.directory.Directory, "augment",
                   lambda self, r: r)
        p = self.load_policy({
            "name": "fsx-windows-must-use-managed-ad",
            "resource": "aws.fsx",
            "filters": [
                {"FileSystemType": "WINDOWS"},
                {"or": [
                    {"type": "value",
                     "key": "WindowsConfiguration.ActiveDirectoryId",
                     "value": "absent"},
                    {"type": "directory", "key": "DirectoryId", "value": "absent"},
                    {"type": "directory", "key": "Type",
                     "value": ["MicrosoftAD", "SharedMicrosoftAD"],
                     "op": "not-in"}]}]})
        selfmanaged = {
            "FileSystemId": "fs-self", "FileSystemType": "WINDOWS",
            "WindowsConfiguration": {
                "SelfManagedActiveDirectoryConfiguration": {
                    "DomainName": "corp.example.com", "DnsIps": ["192.168.1.1"]}}}
        managed = {
            "FileSystemId": "fs-managed", "FileSystemType": "WINDOWS",
            "WindowsConfiguration": {"ActiveDirectoryId": "d-managed"}}
        self.patch(c7n.resources.fsx.FSxDirectoryFilter, "get_related",
                   lambda self, resources: {"d-managed": directories[0]})
        matched = self.run_filters(p, [selfmanaged, managed])
        self.assertEqual([r["FileSystemId"] for r in matched], ["fs-self"])

    def run_filters(self, policy, resources):
        for f in policy.resource_manager.filters:
            resources = f.process(resources)
        return resources


class TestFSxStorageVirtualMachineTags(BaseTest):

    def test_svm_tag_and_remove_tag(self):
        session_factory = self.replay_flight_data("test_fsx_svm_tag")
        p = self.load_policy({
            "name": "fsx_svm_tag",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{"tag:Env": "absent"}],
            "actions": [{"type": "tag", "key": "Env", "value": "Prod"}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            "name": "fsx_svm_remove_tag",
            "resource": "aws.fsx-storage-virtual-machine",
            "filters": [{"tag:Env": "Prod"}],
            "actions": [{"type": "remove-tag", "tags": ["Env"]}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {t["Key"]: t["Value"] for t in resources[0]["Tags"]}["Env"], "Prod")


class TestFSxOntapWithoutStorageVirtualMachine(BaseTest):

    def test_ontap_with_no_svm_is_matched(self):
        session_factory = self.replay_flight_data("test_fsx_ontap_without_svm")
        p = self.load_policy({
            "name": "fsx-ontap-without-svm",
            "resource": "aws.fsx",
            "filters": [
                {"FileSystemType": "ONTAP"},
                {"type": "svm", "count": 0}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:StorageVirtualMachines"], [])


class TestFSxSecurityGroupStaleEni(BaseTest):

    def test_a_departed_eni_doesnt_discard_the_batch(self):
        # a file system being deleted can still reference an eni that has
        # gone, the batch lookup fails and the rest are resolved singly.
        session_factory = self.replay_flight_data("test_fsx_security_group_stale_eni")
        p = self.load_policy({
            "name": "fsx_sg_stale_eni",
            "resource": "aws.fsx",
            "filters": [{"type": "security-group", "key": "GroupName", "value": "fsx-prod"}],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["c7n:matched-security-groups"], ["sg-0prod00000000000a"])
