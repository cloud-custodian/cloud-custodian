# Copyright 2018 Capital One Services, LLC
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

from .common import BaseTest


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
            import time
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
            import time
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
