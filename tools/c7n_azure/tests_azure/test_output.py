# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import os
import shutil
from datetime import date
from unittest import mock

from azure.common import AzureHttpError
from .azure_common import BaseTest
import re
from c7n_azure.output import AzureStorageOutput
from c7n.utils import local_session

from c7n.config import Bag, Config
from c7n.ctx import ExecutionContext
from c7n_azure.session import Session

from c7n_azure.output import MetricsOutput, AppInsightsLogOutput
from c7n.output import log_outputs, metrics_outputs
from mock import patch


class OutputTest(BaseTest):
    def setUp(self):
        super(OutputTest, self).setUp()

    def get_azure_output(self, custom_pyformat=None):
        output_dir = "azure://mystorage.blob.core.windows.net/logs"
        if custom_pyformat:
            output_dir = AzureStorageOutput.join(output_dir, custom_pyformat)

        output = AzureStorageOutput(
            ExecutionContext(
                None,
                Bag(name="xyz", provider_name='azure'),
                Config.empty(output_dir=output_dir)
            ),
            {'url': output_dir},
        )
        self.addCleanup(shutil.rmtree, output.root_dir)

        return output

    def test_azure_output_upload(self):
        # Mock storage utilities to avoid calling azure to get a real client.
        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", 'xyz'

        output = self.get_azure_output()
        self.assertEqual(output.file_prefix, "xyz")

        # Generate fake output file
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        # Mock the create blob call
        output.blob_service = mock.MagicMock()
        output.blob_service.create_blob_from_path = m = mock.MagicMock()

        output.upload()

        m.assert_called_with(
            "logs",
            "xyz/foo.txt",
            fh.name
        )

    def test_azure_output_get_default_output_dir(self):
        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", 'xyz'

        AzureStorageOutput.get_output_vars = mock.Mock(
            return_value={
                'policy_name': 'MyPolicy',
                'now': date(2018, 10, 1)
            })

        output = self.get_azure_output()
        path = output.get_output_path(output.config['url'])
        self.assertEqual(path,
                         'azure://mystorage.blob.core.windows.net/logs/MyPolicy/2018/10/01/00/')

    def test_azure_output_get_custom_output_dir(self):
        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", 'xyz'

        AzureStorageOutput.get_output_vars = mock.Mock(
            return_value={
                'account_id': 'MyAccountId',
                'policy_name': 'MyPolicy',
                'now': date(2018, 10, 1)
            })

        output = self.get_azure_output('{account_id}/{policy_name}/{now:%Y}')
        path = output.get_output_path(output.config['url'])
        self.assertEqual(path,
                         'azure://mystorage.blob.core.windows.net/logs/MyAccountId/MyPolicy/2018')

    def test_app_insights_logs(self):
        policy = Bag(name='test', resource_type='azure.vm', session_factory=Session)
        ctx = Bag(policy=policy, execution_id='00000000-0000-0000-0000-000000000000')
        with log_outputs.select('azure://00000000-0000-0000-0000-000000000000', ctx) as log:
            self.assertTrue(isinstance(log, AppInsightsLogOutput))
            logging.getLogger('custodian.test').warning('test message')

    @patch('c7n_azure.output.MetricsOutput._put_metrics')
    def test_app_insights_metrics(self, put_mock):
        policy = self.load_policy({
            'name': 'test-rg',
            'resource': 'azure.resourcegroup'
        })
        ctx = Bag(policy=policy, execution_id='00000000-0000-0000-0000-000000000000')
        sink = metrics_outputs.select('azure://00000000-0000-0000-0000-000000000000', ctx)
        self.assertTrue(isinstance(sink, MetricsOutput))
        sink.put_metric('ResourceCount', 101, 'Count')
        sink.flush()
        put_mock.assert_called_once_with(
            'test-rg',
            [{
                'Name': 'ResourceCount',
                'Value': 101,
                'Dimensions':
                    {'Policy': 'test-rg',
                     'ResType': 'azure.resourcegroup',
                     'SubscriptionId': local_session(Session).get_subscription_id(),
                     'ExecutionId': '00000000-0000-0000-0000-000000000000',
                     'ExecutionMode': 'pull',
                     'Unit': 'Count'}}])

    @patch('logging.Logger.error')
    def test_access_error(self, logger_mock):

        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", 'xyz'

        output = self.get_azure_output()

        output.blob_service = mock.MagicMock()
        output.blob_service.create_blob_from_path = mock.MagicMock()
        output.blob_service.create_blob_from_path.side_effect = AzureHttpError('forbidden', 403)

        # Generate fake output file
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        output.upload()

        args, _ = logger_mock.call_args

        self.assertIsNotNone(re.match("Access Error*", args[0]))

    @patch('logging.Logger.error')
    def test_error_writing_to_blob(self, logger_mock):
        AzureStorageOutput.get_blob_client_wrapper = gm = mock.MagicMock()
        gm.return_value = None, "logs", 'xyz'

        output = self.get_azure_output()

        output.blob_service = mock.MagicMock()
        output.blob_service.create_blob_from_path = mock.MagicMock()
        output.blob_service.create_blob_from_path.side_effect = AzureHttpError('not found', 404)

        # Generate fake output file
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")

        output.upload()

        args, _ = logger_mock.call_args

        self.assertIsNone(re.match("Access Error*", args[0]))
        self.assertIsNotNone(re.match("Error*", args[0]))
