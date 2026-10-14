# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from azure.common import AzureHttpError
from .azure_common import BaseTest, arm_template
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities
from unittest.mock import patch
from c7n_azure.actions.notify import Notify
import re
from c7n.utils import local_session


class NotifyTest(BaseTest):
    def setUp(self):
        super(NotifyTest, self).setUp()
        self.session = Session()

    def test_notify_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-notify-for-keyvault',
                'resource': 'azure.keyvault',
                'actions': [
                    {'type': 'notify',
                     'template': 'default',
                     'priority_header': '2',
                     'subject': 'testing notify action',
                     'to': ['user@domain.com'],
                     'transport':
                         {'type': 'asq',
                          'queue': ''}
                     }
                ]}, validate=True)
            self.assertTrue(p)

    @arm_template('keyvault.json')
    @pytest.mark.skiplive
    def test_notify_though_storage_queue(self):
        account = self.setup_account()

        # Create queue, make sure it is empty
        queue_url = "https://" + account.name + ".queue.core.windows.net/testnotify"
        queue, name = StorageUtilities.get_queue_client_by_uri(queue_url, self.session)
        queue.clear_messages(name)

        p = self.load_policy({
            'name': 'test-notify-for-keyvault',
            'resource': 'azure.keyvault',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cckeyvault1*'}],
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'asq',
                      'queue': queue_url}
                 }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Pull messages, should be 1
        messages = StorageUtilities.get_queue_messages(queue, name)
        self.assertEqual(len(messages), 1)

    @patch('c7n_azure.storage_utils.StorageUtilities.put_queue_message')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_queue_client_by_uri')
    @patch('logging.Logger.error')
    def test_access_error(self,
                          logger_mock,
                          get_queue_client_by_uri,
                          put_queue_message):
        put_queue_message.side_effect = AzureHttpError('forbidden', 403)
        get_queue_client_by_uri.return_value = 'service', 'name'

        action = Notify()

        action.send_to_azure_queue("url", "message", local_session(Session))

        args, _ = logger_mock.call_args

        self.assertIsNotNone(re.match("Access Error*", args[0]))

    @patch('c7n_azure.storage_utils.StorageUtilities.put_queue_message')
    @patch('c7n_azure.storage_utils.StorageUtilities.get_queue_client_by_uri')
    @patch('logging.Logger.error')
    def test_error_putting_to_queue(self,
                                    logger_mock,
                                    get_queue_client_by_uri,
                                    put_queue_message):
        put_queue_message.side_effect = AzureHttpError('not found', 404)
        get_queue_client_by_uri.return_value = 'service', 'name'

        action = Notify()

        action.send_to_azure_queue("url", "message", local_session(Session))

        args, _ = logger_mock.call_args

        self.assertIsNone(re.match("Access Error*", args[0]))
        self.assertIsNotNone(re.match("Error*", args[0]))
