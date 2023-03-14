# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest

from c7n_mailer.azure_mailer.utils import azure_decrypt
from mock import Mock


class AzureUtilsTest(unittest.TestCase):
    def test_azure_decrypt_raw(self):
        self.assertEqual(azure_decrypt({"test": "value"}, Mock(), Mock(), "test"), "value")
        self.assertEqual(azure_decrypt({"test": "value"}, Mock(), Mock(), "test"), "value")

    def test_azure_decrypt_secret(self):
        config = {"test": {"secret": "https://ccvault.vault.azure.net/secrets/password"}}
        session_mock = Mock()
        session_mock.client().get_secret().value = "value"
        session_mock.get_session_for_resource.return_value = session_mock

        self.assertEqual(azure_decrypt(config, Mock(), session_mock, "test"), "value")
