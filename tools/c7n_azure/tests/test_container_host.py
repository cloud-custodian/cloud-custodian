# Copyright 2019 Microsoft Corporation
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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import shutil

from azure.storage.queue.models import QueueMessage
from mock import ANY, Mock, patch

from azure_common import BaseTest
from c7n_azure.container_host.host import Host

DEFAULT_EVENT_QUEUE_ID = "event-queue-id"
DEFAULT_EVENT_QUEUE_NAME = "event-queue-name"
DEFAULT_POLICY_STORAGE = "policy-storage"


class ContainerHostTest(BaseTest):
    def test_build_options(self):
        result = Host.build_options(
            output_dir='/test/dir',
            log_group='test_log_group',
            metrics='test_metrics'
        )

        self.assertEqual('test_log_group', result['log_group'])
        self.assertEqual('/test/dir', result['output_dir'])
        self.assertEqual('test_metrics', result['metrics'])

    @patch('tempfile.mkdtemp', return_value='test_path')
    def test_build_options_empty(self, _):
        result = Host.build_options()

        self.assertEqual(None, result['log_group'])
        self.assertEqual('test_path', result['output_dir'])
        self.assertEqual(None, result['metrics'])

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('tempfile.mkdtemp', return_value='test_path')
    def test_init(self, _1, _2, _3, _4):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        jobs = host.scheduler.get_jobs()
        update_policy_job = [j for j in jobs if j.id == 'update_policies']
        poll_queue_job = [j for j in jobs if j.id == 'poll_queue']

        self.assertEqual('test_path', host.policy_cache)
        self.assertEqual(2, len(jobs))
        self.assertIsNotNone(update_policy_job)
        self.assertIsNotNone(poll_queue_job)

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies(self, get_blob_client_mock, _1, _2, _3):
        # mock blob list call
        client_mock = Mock()
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", "hash1"),
            ContainerHostTest.get_mock_blob("blob2.YAML", "hash2"),
            ContainerHostTest.get_mock_blob("blob3.md", "hash3")
        ]

        client_mock.get_blob_to_path = self.download_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)

        # init
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # cleanup
        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))

        self.assertEqual({}, host.policies)

        # run
        host.update_policies()

        # both policies were loaded
        self.assertEqual(2, len(host.policies.items()))

        # jobs were created
        jobs = host.scheduler.get_jobs()
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob1.yml']))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob2.YAML']))

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_add_remove(self, get_blob_client_mock, _1, _2, _3):
        """
        Run a series of add/update/removal of policy blobs
        and verify jobs and caches are updated correctly
        """
        # mock blob list call
        client_mock = Mock()
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", "hash1")
        ]

        client_mock.get_blob_to_path = self.download_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)

        # init
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # cleanup
        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))

        self.assertEqual({}, host.policies)

        # Initial load
        host.update_policies()
        self.assertEqual(1, len(host.policies.items()))

        ##################
        # Add two policies
        ##################
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", "hash1"),
            ContainerHostTest.get_mock_blob("blob2.yml", "hash2"),
            ContainerHostTest.get_mock_blob("blob3.yml", "hash3")
        ]

        host.update_policies()
        self.assertEqual(3, len(host.policies.items()))
        self.assertIsNotNone(host.policies['blob1.yml'])
        self.assertIsNotNone(host.policies['blob2.yml'])
        self.assertIsNotNone(host.policies['blob3.yml'])

        # jobs were updated
        jobs = host.scheduler.get_jobs()
        self.assertEqual(3, len([j for j in jobs if j.func == host.run_policy]))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob1.yml']))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob2.yml']))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob3.yml']))

        ##############################################
        # Add one, remove one, update one
        ##############################################
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", "hash1"),
            ContainerHostTest.get_mock_blob("blob4.yml", "hash4"),
            ContainerHostTest.get_mock_blob("blob3.yml", "hash3_new")
        ]

        host.update_policies()
        self.assertEqual(3, len(host.policies.items()))
        self.assertIsNotNone(host.policies['blob1.yml'])
        self.assertIsNotNone(host.policies['blob4.yml'])
        self.assertIsNotNone(host.policies['blob3.yml'])
        self.assertEqual('hash3_new', host.blob_cache['blob3.yml'])

        # jobs were updated
        jobs = host.scheduler.get_jobs()
        self.assertEqual(3, len([j for j in jobs if j.func == host.run_policy]))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob1.yml']))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob4.yml']))
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob3.yml']))

        ############
        # remove all
        ############
        client_mock.list_blobs.return_value = [
        ]

        host.update_policies()
        self.assertEqual(0, len(host.policies.items()))

        # jobs were updated
        jobs = host.scheduler.get_jobs()
        self.assertEqual(0, len([j for j in jobs if j.func == host.run_policy]))

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Host.update_policies')
    @patch('c7n_azure.container_host.host.AzureEventSubscription')
    @patch('c7n_azure.container_host.host.StringInAdvancedFilter')
    def test_update_event_subscriptions(self, event_filter_mock, _0, _1, _2, _3, _4):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        host.event_queue_name = 'testq'

        host.policies = {
            'one': {
                'policy': ContainerHostTest.get_mock_policy({
                    'name': 'one',
                    'mode': {
                        'type': 'container-event',
                        'events': ['ResourceGroupWrite', 'VnetWrite']
                    }
                })
            },
            'two': {
                'policy': ContainerHostTest.get_mock_policy({
                    'name': 'two',
                    'mode': {
                        'type': 'container-event',
                        'events': ['ResourceGroupWrite']
                    }
                })
            },
            'three': {
                'policy': ContainerHostTest.get_mock_policy({
                    'name': 'three',
                    'mode': {
                        'type': 'container-event',
                        'events': [{
                            'resourceProvider': 'Microsoft.KeyVault/vaults',
                            'event': 'write'
                        }]
                    }
                })
            }
        }

        # Verify we get all three events with no duplicates
        host.update_event_subscriptions()
        event_filter_mock.assert_called_with(key='Data.OperationName', values={
            'Microsoft.KeyVault/vaults/write',
            'Microsoft.Network/virtualNetworks/write',
            'Microsoft.Resources/subscriptions/resourceGroups/write'})

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage')
    @patch('c7n_azure.container_host.host.Host.run_policies_for_event')
    def test_poll_queue(self, run_policy_mock, storage_mock, _1, _2):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        host.policies = {
            'one': {
                'policy': ContainerHostTest.get_mock_policy({
                    'name': 'one',
                    'mode': {
                        'type': 'container-event',
                        'events': ['ResourceGroupWrite', 'VnetWrite']
                    }
                })
            }
        }

        q1 = QueueMessage()
        q1.id = 1
        q1.dequeue_count = 0
        q1.content = """eyAgCiAgICJzdWJqZWN0IjoiL3N1YnNjcmlwdGlvbnMvZWE5ODk3NGItNWQyYS00ZDk4LWE3
        OGEtMzgyZjM3MTVkMDdlL3Jlc291cmNlR3JvdXBzL3Rlc3RfY29udGFpbmVyX21vZGUiLAogICAiZXZlbnRUeXBlIj
        oiTWljcm9zb2Z0LlJlc291cmNlcy5SZXNvdXJjZVdyaXRlU3VjY2VzcyIsCiAgICJldmVudFRpbWUiOiIyMDE5LTA3
        LTE2VDE4OjMwOjQzLjM1OTUyNTVaIiwKICAgImlkIjoiNjE5ZDI2NzQtYjM5Ni00MzU2LTk2MTktNmM1YTUyZmU0ZT
        g4IiwKICAgImRhdGEiOnsgICAgICAgIAogICAgICAiY29ycmVsYXRpb25JZCI6IjdkZDVhNDc2LWUwNTItNDBlMi05
        OWU0LWJiOTg1MmRjMWY4NiIsCiAgICAgICJyZXNvdXJjZVByb3ZpZGVyIjoiTWljcm9zb2Z0LlJlc291cmNlcyIsCi
        AgICAgICJyZXNvdXJjZVVyaSI6Ii9zdWJzY3JpcHRpb25zL2VhOTg5NzRiLTVkMmEtNGQ5OC1hNzhhLTM4MmYzNzE1
        ZDA3ZS9yZXNvdXJjZUdyb3Vwcy90ZXN0X2NvbnRhaW5lcl9tb2RlIiwKICAgICAgIm9wZXJhdGlvbk5hbWUiOiJNaW
        Nyb3NvZnQuUmVzb3VyY2VzL3N1YnNjcmlwdGlvbnMvcmVzb3VyY2VHcm91cHMvd3JpdGUiLAogICAgICAic3RhdHVz
        IjoiU3VjY2VlZGVkIiwKICAgfSwKICAgInRvcGljIjoiL3N1YnNjcmlwdGlvbnMvYWE5ODk3NGItNWQyYS00ZDk4LW
        E3OGEtMzgyZjM3MTVkMDdlIgp9"""

        q2 = QueueMessage()
        q2.id = 2
        q2.dequeue_count = 0
        q2.content = q1.content

        # Return 2 messages on first call, then none
        storage_mock.get_queue_messages.side_effect = [[q1, q2], []]
        host.poll_queue()
        self.assertEqual(2, run_policy_mock.call_count)
        run_policy_mock.reset_mock()

        # Return 5 messages on first call, then 2, then 0
        storage_mock.get_queue_messages.side_effect = [[q1, q1, q1, q1, q1], [q1, q2], []]
        host.poll_queue()
        self.assertEqual(7, run_policy_mock.call_count)
        run_policy_mock.reset_mock()

        # High dequeue count
        q1.dequeue_count = 100
        storage_mock.get_queue_messages.side_effect = [[q1, q2], []]
        host.poll_queue()
        self.assertEqual(1, run_policy_mock.call_count)

    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.BlockingScheduler.add_job')
    def test_run_policy_for_event(self, add_job_mock, _0, _1, _2):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        host.policies = {
            'one': {
                'policy': ContainerHostTest.get_mock_policy({
                    'name': 'one',
                    'mode': {
                        'type': 'container-event',
                        'events': ['ResourceGroupWrite', 'VnetWrite']
                    }
                })
            }
        }

        message = QueueMessage()
        message.id = 1
        message.dequeue_count = 0
        message.content = \
            """eyAgCiAgICJzdWJqZWN0IjoiL3N1YnNjcmlwdGlvbnMvZWE5ODk3NGItNWQyYS00ZDk4LWE3OGEt
            MzgyZjM3MTVkMDdlL3Jlc291cmNlR3JvdXBzL3Rlc3RfY29udGFpbmVyX21vZGUiLAogICAiZXZl
            bnRUeXBlIjoiTWljcm9zb2Z0LlJlc291cmNlcy5SZXNvdXJjZVdyaXRlU3VjY2VzcyIsCiAgICJl
            dmVudFRpbWUiOiIyMDE5LTA3LTE2VDE4OjMwOjQzLjM1OTUyNTVaIiwKICAgImlkIjoiNjE5ZDI2
            NzQtYjM5Ni00MzU2LTk2MTktNmM1YTUyZmU0ZTg4IiwKICAgImRhdGEiOnsgICAgICAgIAogICAg
            ICAiY29ycmVsYXRpb25JZCI6IjdkZDVhNDc2LWUwNTItNDBlMi05OWU0LWJiOTg1MmRjMWY4NiIs
            CiAgICAgICJyZXNvdXJjZVByb3ZpZGVyIjoiTWljcm9zb2Z0LlJlc291cmNlcyIsCiAgICAgICJy
            ZXNvdXJjZVVyaSI6Ii9zdWJzY3JpcHRpb25zL2VhOTg5NzRiLTVkMmEtNGQ5OC1hNzhhLTM4MmYz
            NzE1ZDA3ZS9yZXNvdXJjZUdyb3Vwcy90ZXN0X2NvbnRhaW5lcl9tb2RlIiwKICAgICAgIm9wZXJh
            dGlvbk5hbWUiOiJNaWNyb3NvZnQuUmVzb3VyY2VzL3N1YnNjcmlwdGlvbnMvcmVzb3VyY2VHcm91
            cHMvd3JpdGUiLAogICAgICAic3RhdHVzIjoiU3VjY2VlZGVkIgogICB9LAogICAidG9waWMiOiIv
            c3Vic2NyaXB0aW9ucy9hYTk4OTc0Yi01ZDJhLTRkOTgtYTc4YS0zODJmMzcxNWQwN2UiCn0="""

        # run with real match
        host.run_policies_for_event(message)
        add_job_mock.assert_called_with(ANY,
                                        id='one619d2674-b396-4356-9619-6c5a52fe4e88',
                                        name='one',
                                        args=ANY,
                                        misfire_grace_time=ANY)

        add_job_mock.reset_mock()

        # run with no match
        host.policies = {}
        host.run_policies_for_event(message)
        self.assertFalse(add_job_mock.called)

    @staticmethod
    def download_policy_blob(_, name, path):
        policy_string = """
                            policies:
                              - name: %s
                                mode:
                                  type: container-periodic
                                  schedule: '* * * * *'
                                resource: azure.resourcegroup
                        """

        with open(path, 'w') as out_file:
            out_file.write(policy_string % name)

    @staticmethod
    def get_mock_blob(name, md5):
        new_blob = Mock()
        new_blob.name = name
        new_blob.properties.content_settings.content_md5 = md5
        return new_blob

    @staticmethod
    def get_mock_policy(policy):
        new_policy = Mock()
        new_policy.data = policy
        return new_policy
