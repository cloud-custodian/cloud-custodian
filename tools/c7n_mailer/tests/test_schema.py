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

import c7n_mailer.cli as cli
import jsonschema
import jsonschema.exceptions as exceptions


class MailerSchemaTest(unittest.TestCase):

    def test_validate_secured_string(self):
        property_schema = {'type': 'object', 'properties': {'test': cli.SECURED_STRING_SCHEMA}}
        jsonschema.validate({'test': 'raw_string'}, property_schema)
        jsonschema.validate({'test': {'type': 'azure.keyvault',
                                      'secret': 'https://secret_uri'}}, property_schema)

        with self.assertRaises(exceptions.ValidationError):
            jsonschema.validate({'test': {'wrong': 'value'}},
                                property_schema)
            jsonschema.validate({'test': {'secret': 'https://secret_uri'}},
                                property_schema)
            jsonschema.validate({'test': {'type': 'azure.keyvault',
                                          'secret': 'https://secret_uri', 'extra': 'e'}},
                                property_schema)
