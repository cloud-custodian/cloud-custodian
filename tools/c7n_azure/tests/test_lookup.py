# Copyright 2019 Microsoft Corp
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

from azure_common import BaseTest

from c7n_azure.tags import Lookup


class TagsTest(BaseTest):

    def test_extract_no_lookup(self):
        source = 'mock_string_value'
        value = Lookup.extract(source)
        self.assertEqual(source, value)

    def test_extract_lookup(self):
        data = {
            'field_level_1': {
                'field_level_2': 'value_1'
            }
        }
        source = {
            Lookup.RESOURCE_SOURCE: 'field_level_1.field_level_2',
            'default-value': 'value_2'
        }

        value = Lookup.extract(source, data)
        self.assertEqual(value, 'value_1')

    def test_get_value_from_resource_value_exists(self):
        resource = {
            'field_level_1': {
                'field_level_2': 'value_1'
            }
        }
        source = {
            Lookup.RESOURCE_SOURCE: 'field_level_1.field_level_2',
            'default-value': 'value_2'
        }

        value = Lookup.get_value_from_resource(source, resource)
        self.assertEqual(value, 'value_1')

    def test_get_value_from_resource_value_not_exists(self):
        resource = {
            'field_level_1': {
                'field_level_2': None
            }
        }
        source = {
            Lookup.RESOURCE_SOURCE: 'field_level_1.field_level_2',
            'default-value': 'value_2'
        }

        value = Lookup.get_value_from_resource(source, resource)
        self.assertEqual(value, 'value_2')

    def test_get_value_from_resource_value_not_exists_exception(self):
        resource = {
            'field_level_1': {
                'field_level_2': None
            }
        }
        source = {
            Lookup.RESOURCE_SOURCE: 'field_level_1.field_level_2'
        }

        with self.assertRaises(Exception):
            Lookup.get_value_from_resource(source, resource)
