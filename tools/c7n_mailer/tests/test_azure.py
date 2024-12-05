# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import unittest
import zlib

from mock import ANY, MagicMock, Mock, call, patch

from c7n_azure.storage_utils import StorageUtilities
from c7n_mailer.azure_mailer import deploy
from c7n_mailer.azure_mailer.azure_queue_processor import MailerAzureQueueProcessor
from c7n_mailer.azure_mailer.sendgrid_delivery import SendGridDelivery
from common import (
    ASQ_MESSAGE,
    ASQ_MESSAGE_DATADOG,
    ASQ_MESSAGE_MULTIPLE_ADDRS,
    ASQ_MESSAGE_SLACK,
    ASQ_MESSAGE_TAG,
    MAILER_CONFIG_AZURE,
    logger,
)


class AzureTest(unittest.TestCase):
    def setUp(self):
        self.compressed_message = MagicMock()
        self.compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE.encode("utf8"))
        )
        self.loaded_message = json.loads(ASQ_MESSAGE)

        self.tag_message = json.loads(ASQ_MESSAGE_TAG)

        self.multiple_addrs_message = json.loads(ASQ_MESSAGE_MULTIPLE_ADDRS)

    @patch("c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler")
    @patch(
        "c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery"
        ".get_to_addrs_sendgrid_messages_map"
    )
    def test_process_azure_queue_message_success(self, mock_get_addr, mock_handler):
        mock_handler.return_value = True
        mock_get_addr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertTrue(
            azure_processor.process_azure_queue_message(self.compressed_message, "timestamp")
        )

        # Verify mock calls were correct
        mock_get_addr.assert_called_with(self.loaded_message)
        mock_handler.assert_called_with(self.loaded_message, 42)

    @patch("c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery.sendgrid_handler")
    @patch(
        "c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery"
        ".get_to_addrs_sendgrid_messages_map"
    )
    def test_process_azure_queue_message_failure(self, mock_get_addr, mock_handler):
        mock_handler.return_value = False
        mock_get_addr.return_value = 42

        # Run the process messages method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        self.assertFalse(
            azure_processor.process_azure_queue_message(self.compressed_message, "timestamp")
        )

        # Verify mock calls were correct
        mock_get_addr.assert_called_with(self.loaded_message)
        mock_handler.assert_called_with(self.loaded_message, 42)

    @patch.object(MailerAzureQueueProcessor, "process_azure_queue_message")
    @patch.object(StorageUtilities, "get_queue_client_by_uri")
    @patch.object(StorageUtilities, "delete_queue_message")
    @patch.object(StorageUtilities, "get_queue_messages")
    def test_run(self, mock_get_messages, mock_delete, mock_client, mock_process):
        mock_get_messages.side_effect = [[self.compressed_message], []]
        mock_client.return_value = (None, None)
        mock_process.return_value = True

        # Run the 'run' method
        azure_processor = MailerAzureQueueProcessor(MAILER_CONFIG_AZURE, logger)
        azure_processor.run(False)

        self.assertEqual(2, mock_get_messages.call_count)
        self.assertEqual(1, mock_process.call_count)
        mock_delete.assert_called()

    @patch("sendgrid.SendGridAPIClient.send")
    def test_sendgrid_handler(self, mock_send):
        sendgrid_delivery = SendGridDelivery(MAILER_CONFIG_AZURE, Mock(), logger)
        sendgrid_messages = sendgrid_delivery.get_to_addrs_sendgrid_messages_map(
            self.loaded_message
        )
        result = sendgrid_delivery.sendgrid_handler(self.loaded_message, sendgrid_messages)
        self.assertTrue(result)
        mock_send.assert_called_once()
        mail_contents = mock_send.call_args[0][0].contents[0].content
        self.assertIn("The following azure.keyvault resources", mail_contents)

    @patch("sendgrid.SendGridAPIClient.send")
    def test_sendgrid_handler_multiple_to_addrs(self, mock_send):
        sendgrid_delivery = SendGridDelivery(MAILER_CONFIG_AZURE, Mock(), logger)
        sendgrid_messages = sendgrid_delivery.get_to_addrs_sendgrid_messages_map(
            self.multiple_addrs_message
        )
        result = sendgrid_delivery.sendgrid_handler(self.multiple_addrs_message, sendgrid_messages)
        self.assertTrue(result)
        self.assertEqual(2, mock_send.call_count)
        mail_contents = mock_send.call_args[0][0].contents[0].content
        self.assertIn("The following azure.keyvault resources", mail_contents)

        address_one = mock_send.call_args_list[0][0][0].personalizations[0].tos[0]["email"]
        self.assertEqual("user2@domain.com", address_one)
        address_two = mock_send.call_args_list[1][0][0].personalizations[0].tos[0]["email"]
        self.assertEqual("user@domain.com", address_two)

    def test_azure_mailer_requirements(self):
        reqs = deploy.get_mailer_requirements()
        self.assertIn("adal", reqs)
        self.assertIn("azure-storage-blob", reqs)
        self.assertIn("azure-storage-queue", reqs)
        self.assertIn("azure-common", reqs)
        self.assertIn("azure-mgmt-managementgroups", reqs)
        self.assertIn("azure-mgmt-web", reqs)
        self.assertIn("azure-graphrbac", reqs)
        self.assertIn("msrestazure", reqs)
        self.assertIn("jmespath", reqs)
        self.assertIn("jinja2", reqs)
        self.assertIn("sendgrid", reqs)
        self.assertIn("ldap3", reqs)
        self.assertIn("netaddr", reqs)

    @patch("c7n_mailer.azure_mailer.deploy.FunctionPackage")
    def test_build_function_package(self, package_mock):
        deploy.build_function_package(MAILER_CONFIG_AZURE, "test_mailer", "sub")

        package_mock.assert_called_with(
            "test_mailer", ANY, target_sub_ids=["sub"], cache_override_path=deploy.cache_path()
        )

        package_mock.return_value.pkg.add_contents.assert_any_call(
            "test_mailer_sub/config.json", contents=ANY
        )

        package_mock.return_value.pkg.add_contents.assert_any_call(
            "test_mailer_sub/function.json", contents=ANY
        )

    @patch("c7n_mailer.azure_mailer.deploy.build_function_package")
    @patch("c7n_mailer.azure_mailer.deploy.FunctionAppUtilities")
    @patch("c7n_mailer.azure_mailer.deploy.Session")
    @patch("c7n_mailer.azure_mailer.deploy.local_session")
    def test_provision_embedded_auth(
        self, mock_local_session, mock_session, mock_func_utils, mock_build_pkg
    ):
        mock_session.get_subscription_id.return_value = "mock-id"
        mock_local_session.return_value = mock_session
        mock_func_utils.get_function_name.return_value = "mock-func-name"
        mock_build_pkg.return_value = MagicMock()

        deploy.provision(MAILER_CONFIG_AZURE)

        mock_func_utils.FunctionAppInfrastructureParameters.assert_called_with(
            app_insights=ANY,
            service_plan=ANY,
            storage_account=ANY,
            function_app={
                "resource_group_name": "cloud-custodian",
                "identity": {"type": "Embedded"},
                "name": "mock-func-name",
            },
        )

        mock_func_utils.deploy_function_app.assert_called_once()
        mock_func_utils.publish_functions_package.assert_called_once()

    @patch("c7n_mailer.azure_mailer.deploy.build_function_package")
    @patch("c7n_mailer.azure_mailer.deploy.FunctionAppUtilities")
    @patch("c7n_mailer.azure_mailer.deploy.Session")
    @patch("c7n_mailer.azure_mailer.deploy.local_session")
    def test_provision_msi_auth(
        self, mock_local_session, mock_session, mock_func_utils, mock_build_pkg
    ):
        mock_session.get_subscription_id.return_value = "mock-id"
        mock_local_session.return_value = mock_session
        mock_func_utils.get_function_name.return_value = "mock-func-name"
        mock_build_pkg.return_value = MagicMock()
        system_assigned = {"identity": {"type": "SystemAssigned"}}

        with patch.dict(MAILER_CONFIG_AZURE, {"function_properties": system_assigned}):
            deploy.provision(MAILER_CONFIG_AZURE)

            mock_func_utils.FunctionAppInfrastructureParameters.assert_called_with(
                app_insights=ANY,
                service_plan=ANY,
                storage_account=ANY,
                function_app={
                    "resource_group_name": "cloud-custodian",
                    "identity": {"type": "SystemAssigned"},
                    "name": "mock-func-name",
                },
            )

            mock_func_utils.deploy_function_app.assert_called_once()
            mock_func_utils.publish_functions_package.assert_called_once()

    @patch("c7n_mailer.azure_mailer.deploy.build_function_package")
    @patch("c7n_mailer.azure_mailer.deploy.FunctionAppUtilities")
    @patch("c7n_mailer.azure_mailer.deploy.Session")
    @patch("c7n_mailer.azure_mailer.deploy.local_session")
    def test_provision_uai_auth(
        self, mock_local_session, mock_session, mock_func_utils, mock_build_pkg
    ):
        mock_session.get_subscription_id.return_value = "mock-id"
        mock_local_session.return_value = mock_session
        mock_func_utils.get_function_name.return_value = "mock-func-name"
        mock_build_pkg.return_value = MagicMock()
        user_assigned = {
            "identity": {"type": "UserAssigned", "id": "mock-id", "client_id": "mock-client-id"}
        }

        with patch.dict(MAILER_CONFIG_AZURE, {"function_properties": user_assigned}):
            deploy.provision(MAILER_CONFIG_AZURE)

            mock_func_utils.FunctionAppInfrastructureParameters.assert_called_with(
                app_insights=ANY,
                service_plan=ANY,
                storage_account=ANY,
                function_app={
                    "resource_group_name": "cloud-custodian",
                    "identity": {
                        "type": "UserAssigned",
                        "id": "mock-id",
                        "client_id": "mock-client-id",
                    },
                    "name": "mock-func-name",
                },
            )

            mock_func_utils.deploy_function_app.assert_called_once()
            mock_func_utils.publish_functions_package.assert_called_once()

    @patch("c7n_mailer.azure_mailer.azure_queue_processor.SmtpDelivery")
    def test_smtp_delivery(self, mock_smtp):
        smtp_mailer_config = {
            "queue_url": "asq://storageaccount.queue.core.windows.net/queuename",
            "from_address": "you@youremail.com",
            "smtp_port": 25,
            "smtp_ssl": True,
            "smtp_server": "test_server",
            "smtp_username": "user",
            "smtp_password": "password",
        }

        with patch(
            "c7n_mailer.azure_mailer.sendgrid_delivery.SendGridDelivery"
            ".get_to_addrs_sendgrid_messages_map",
            return_value={("mock@test.com",): self.loaded_message},
        ):
            azure_processor = MailerAzureQueueProcessor(smtp_mailer_config, logger)
            self.assertTrue(
                azure_processor.process_azure_queue_message(self.compressed_message, "timestamp")
            )
            mock_smtp.assert_has_calls(
                [call().send_message(message=self.loaded_message, to_addrs=["mock@test.com"])]
            )

    @patch("c7n_mailer.slack_delivery.SlackDelivery")
    def test_slack_delivery(self, mock_slack):
        slack_mailer_config = {
            "queue_url": "asq://storageaccount.queue.core.windows.net/queuename",
            "slack_token": "mock_token",
        }

        slack_compressed_message = MagicMock()
        slack_compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE_SLACK.encode("utf8"))
        )
        slack_loaded_message = json.loads(ASQ_MESSAGE_SLACK)

        mock_slack.return_value.get_to_addrs_slack_messages_map.return_value = (
            "mock_slack_message_map"
        )

        azure_processor = MailerAzureQueueProcessor(slack_mailer_config, logger)

        self.assertTrue(
            azure_processor.process_azure_queue_message(slack_compressed_message, "timestamp")
        )
        mock_slack.assert_has_calls(
            [call().slack_handler(slack_loaded_message, "mock_slack_message_map")]
        )

    @patch("c7n_mailer.datadog_delivery.DataDogDelivery")
    def test_datadog_delivery(self, mock_datadog):
        datadog_mailer_config = {
            "queue_url": "asq://storageaccount.queue.core.windows.net/queuename",
            "datadog_api_key": "mock_api_key",
            "datadog_application_key": "mock_application_key",
        }

        datadog_compressed_message = MagicMock()
        datadog_compressed_message.content = base64.b64encode(
            zlib.compress(ASQ_MESSAGE_DATADOG.encode("utf8"))
        )
        datadog_loaded_message = json.loads(ASQ_MESSAGE_DATADOG)

        mock_datadog.return_value.get_datadog_message_packages.return_value = (
            "mock_datadog_message_map"
        )

        azure_processor = MailerAzureQueueProcessor(datadog_mailer_config, logger)

        self.assertTrue(
            azure_processor.process_azure_queue_message(datadog_compressed_message, "timestamp")
        )
        mock_datadog.assert_has_calls(
            [call().deliver_datadog_messages("mock_datadog_message_map", datadog_loaded_message)]
        )
