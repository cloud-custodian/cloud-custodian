# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest, CUSTOM_SUBSCRIPTION_ID
from c7n_azure.handler import run
from os.path import dirname, join
from c7n.config import Config
from mock import patch, call


class HandlerTest(BaseTest):

    @patch('c7n_azure.provider.Azure.initialize', return_value=Config.empty())
    @patch('azure.common.credentials.ServicePrincipalCredentials.__init__', return_value=None)
    @patch('c7n.policy.Policy.push')
    def test_run(self, push_mock, _1, initialize_mock):
        context = {
            'config_file': join(dirname(__file__), 'data', 'test_config.json'),
            'auth_file': join(dirname(__file__), 'data', 'test_auth_file.json')
        }

        self.assertTrue(run(None, context, CUSTOM_SUBSCRIPTION_ID))

        push_mock.assert_called_once()
        self.assertEqual(push_mock.call_args_list[0], call(None, context))

        initialize_mock.assert_called_once()
        self.assertEqual(initialize_mock.call_args_list[0][0][0]['account_id'],
                         CUSTOM_SUBSCRIPTION_ID)
        self.assertEqual(initialize_mock.call_args_list[0][0][0]['authorization_file'],
                         context['auth_file'])
        self.assertEqual(initialize_mock.call_args_list[0][0][0]['test_option'],
                         "test_value")

    def test_run_empty_policy(self):
        context = {
            'config_file': join(dirname(__file__), 'data', 'test_config_empty.json'),
            'auth_file': join(dirname(__file__), 'data', 'test_auth_file.json')
        }

        self.assertFalse(run(None, context))
