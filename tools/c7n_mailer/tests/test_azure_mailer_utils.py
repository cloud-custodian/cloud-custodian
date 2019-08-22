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

import unittest

from c7n_mailer.azure_mailer.utils import azure_decrypt
from mock import Mock


class AzureUtilsTest(unittest.TestCase):

    def test_azure_decrypt_raw(self):
        self.assertEqual(azure_decrypt({'test': 'value'}, Mock(), Mock(), 'test'), 'value')
        self.assertEqual(azure_decrypt({'test': 'value'}, Mock(), Mock(), 'test'), 'value')

    def test_azure_decrypt_secret(self):
        config = {'test': {'secret': 'https://ccvault.vault.azure.net/secrets/password'}}
        session_mock = Mock()
        session_mock.client().get_secret().value = 'value'
        session_mock.get_session_for_resource.return_value = session_mock

        self.assertEqual(azure_decrypt(config, Mock(), session_mock, 'test'), 'value')
