# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
import shutil
import tempfile

import yaml
from azure.common import AzureHttpError
from azure.storage.queue import QueueMessage
from mock import ANY, Mock, patch

from ..azure_common import BaseTest
from c7n_azure.container_host.host import Host

DEFAULT_EVENT_QUEUE_ID = "event-queue-id"
DEFAULT_EVENT_QUEUE_STORAGE_ID = "/subscriptions/11111111-2222-3333-4444-555555555555/"
"resourceGroups/storagerg/providers/Microsoft.Storage/storageAccounts/samplestorage"
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

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('tempfile.mkdtemp', return_value='test_path')
    def test_init(self, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        jobs = host.scheduler.get_jobs()
        update_policy_job = [j for j in jobs if j.id == 'update_policies']
        poll_queue_job = [j for j in jobs if j.id == 'poll_queue']

        self.assertEqual('test_path', host.policy_cache)
        self.assertEqual(2, len(jobs))
        self.assertIsNotNone(update_policy_job)
        self.assertIsNotNone(poll_queue_job)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('tempfile.mkdtemp', return_value='test_path')
    def test_init_different_storage_subscription(self, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_STORAGE_ID,
                    DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        self.assertIsNot(host.storage_session, host.session)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies(self, get_blob_client_mock, _1, _2, _3, _4):
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

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_add_remove(self, get_blob_client_mock, _1, _2, _3, _4):
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

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_create_content_hash(self, get_blob_client_mock, _1, _2, _3, _4):
        client_mock = Mock()
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", None),  # no hash
        ]

        client_mock.get_blob_to_path = self.download_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)

        def get_blob_properties(_, blob_name):
            return ContainerHostTest.get_mock_blob(blob_name, 'hash')  # now with hash
        client_mock.get_blob_properties = get_blob_properties

        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # cleanup
        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))

        self.assertEqual({}, host.policies)

        # run
        host.update_policies()

        # both policies were loaded
        self.assertEqual(1, len(host.policies.items()))

        # jobs were created
        jobs = host.scheduler.get_jobs()
        self.assertEqual(1, len([j for j in jobs if j.id == 'blob1.yml']))

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_ignore_policy_if_failed_to_create_content_hash(self,
            get_blob_client_mock, _1, _2, _3, _4):
        client_mock = Mock()
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob("blob1.yml", None),  # no hash
        ]

        client_mock.get_blob_to_path = self.download_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)

        def create_blob_from_bytes(_1, _2, _3, **kwargs):
            raise AzureHttpError("Failed to create blob", 403)
        client_mock.create_blob_from_bytes = create_blob_from_bytes

        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # cleanup
        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))

        self.assertEqual({}, host.policies)

        # run
        host.update_policies()

        # no policies were loaded
        self.assertEqual(0, len(host.policies.items()))

        # jobs were created
        jobs = host.scheduler.get_jobs()
        self.assertEqual(0, len([j for j in jobs if j.id == 'blob1.yml']))

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_list_blobs_azure_http_error(self,
            get_blob_client_mock, _2, _3, _4, _5):
        client_mock = Mock()
        client_mock.list_blobs.side_effect = AzureHttpError("failed to list blobs", 400)
        get_blob_client_mock.return_value = (client_mock, None, None)

        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        with self.assertRaises(AzureHttpError):
            host.update_policies()
        client_mock.list_blobs.assert_called()

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_update_policies_missing_mode(self, get_blob_client_mock, _2, _3, _4, _5):
        client_mock = Mock()
        client_mock.list_blobs.return_value = [
            ContainerHostTest.get_mock_blob('no-mode-blob.yaml', 'no-mode-blob')
        ]
        client_mock.get_blob_to_path = self.download_missing_mode_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))
        host.update_policies()
        self.assertEqual(1, len(host.policies.items()))

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    @patch('os.makedirs', wraps=os.makedirs)
    def test_update_policies_in_subfolders(self,
            makedirs_mock, get_blob_client_mock, _2, _3, _4, _5):
        blob_name = "path/to/blob.yml"
        client_mock = Mock()
        client_mock.list_blobs.return_value = [ContainerHostTest.get_mock_blob(blob_name, 'blob')]
        client_mock.get_blob_to_path = self.download_policy_blob
        get_blob_client_mock.return_value = (client_mock, None, None)

        self.addCleanup(lambda: shutil.rmtree(host.policy_cache))

        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        host.update_policies()
        self.assertEqual(1, len(host.policies.items()))
        jobs = host.scheduler.get_jobs()
        self.assertEqual(1, len([j for j in jobs if j.id == blob_name]))
        blob_dir = os.path.join(host.policy_cache, blob_name)
        makedirs_mock.assert_any_call(os.path.dirname(blob_dir))

    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Host.update_policies')
    @patch('c7n_azure.container_host.host.AzureEventSubscription')
    @patch('c7n_azure.container_host.host.EventSubscriptionFilter')
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
        host.update_event_subscription()
        event_filter_mock.assert_called_with(
            included_event_types=['Microsoft.Resources.ResourceWriteSuccess'])

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage')
    @patch('c7n_azure.container_host.host.Host.run_policies_for_event')
    def test_poll_queue(self, run_policy_mock, storage_mock, _1, _2, _3):
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

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.BlockingScheduler.add_job')
    def test_run_policy_for_event(self, add_job_mock, _0, _1, _2, _3):
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

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    @patch('yaml.safe_load', side_effect=yaml.YAMLError())
    @patch('os.unlink')
    def test_unload_policy_file_with_yaml_error(self,
            os_unlink, yaml_safe_load, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # Create a bad yaml file
        file_path = tempfile.mktemp(suffix=".yaml")
        with open(file_path, 'w') as f:
            f.write("bad yaml file")

        host.load_policy(file_path, host.policies)
        host.unload_policy_file(file_path, host.policies)
        os_unlink.assert_called()

        # Clean up the file
        os.remove(file_path)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    @patch('os.unlink')
    def test_unload_policy_file_that_was_never_loaded(self,
            os_unlink, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        policy_string = """
                            policies:
                              - name: foo
                                mode:
                                  type: container-periodic
                                  schedule: '* * * * *'
                                resource: azure.resourcegroup
                        """

        # Create a bad yaml file
        file_path = tempfile.mktemp(suffix=".yaml")
        with open(file_path, 'w') as f:
            f.write(policy_string)

        host.unload_policy_file(file_path, {})
        os_unlink.assert_called()

        # Clean up the file
        os.remove(file_path)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    @patch('os.unlink')
    def test_unload_policy_file_without_name(self,
            os_unlink, yaml_safe_load, _1, _2, _3, _4):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # Create a bad yaml file (no name field)
        file_path = tempfile.mktemp(suffix=".yaml")
        with open(file_path, 'w') as f:
            f.write("""
                        policies:
                          - mode:
                              type: container-periodic
                              schedule: '* * * * *'
                            resource: azure.resourcegroup
                        """)

        host.load_policy(file_path, host.policies)
        host.unload_policy_file(file_path, host.policies)
        os_unlink.assert_called()

        # Clean up the file
        os.remove(file_path)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    @patch('os.unlink')
    def test_unload_policy_file_with_bad_schema(self,
            os_unlink, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)

        # Schedule is invalid
        policy_string = """
                            policie:
                              - name: foo
                                mode:
                                  type: container-periodic
                                  schedule: '* * * *'
                                resource: azure.resourcegroup
                        """

        # Create a bad yaml file
        file_path = tempfile.mktemp(suffix=".yaml")
        with open(file_path, 'w') as f:
            f.write(policy_string)

        host.load_policy(file_path, host.policies)
        host.unload_policy_file(file_path, host.policies)
        os_unlink.assert_called()

        # Clean up the file
        os.remove(file_path)

    @patch('c7n_azure.container_host.host.Host.update_event_subscription')
    @patch('c7n_azure.container_host.host.BlockingScheduler.start')
    @patch('c7n_azure.container_host.host.Host.prepare_queue_storage')
    @patch('c7n_azure.container_host.host.Storage.get_queue_client_by_storage_account')
    @patch('c7n_azure.container_host.host.Storage.get_blob_client_by_uri')
    def test_run_policy_handles_exceptions(self, _1, _2, _3, _4, _5):
        host = Host(DEFAULT_EVENT_QUEUE_ID, DEFAULT_EVENT_QUEUE_NAME, DEFAULT_POLICY_STORAGE)
        mock_policy = Mock()
        mock_policy.push.side_effect = Exception()
        host.run_policy(mock_policy, None, None)

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
    def download_missing_mode_policy_blob(_, name, path):
        policy_string = """
                            policies:
                              - name: %s
                                resource: azure.resourcegroup
                        """

        with open(path, 'w') as out_file:
            out_file.write(policy_string % name)

    @staticmethod
    def get_mock_blob(name, md5):
        new_blob = Mock()
        new_blob.name = name
        new_blob.content_settings.content_md5 = md5
        return new_blob

    @staticmethod
    def get_mock_policy(policy):
        new_policy = Mock()
        new_policy.data = policy
        return new_policy
