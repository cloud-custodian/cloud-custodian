# Copyright 2019 Microsoft Corp
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest

from c7n.lookup import Lookup


class LookupTest(BaseTest):

    def test_lookup_type(self):
        number_schema = {'type': 'number'}
        lookup_default_number = Lookup.lookup_type(number_schema)

        string_schema = {'type': 'string'}
        lookup_default_string = Lookup.lookup_type(string_schema)

        self.assertEqual(number_schema, lookup_default_number['oneOf'][1])
        self.assertEqual(number_schema,
                         lookup_default_number['oneOf'][0]['oneOf'][0]
                         ['properties']['default-value'])

        self.assertEqual(string_schema, lookup_default_string['oneOf'][1])
        self.assertEqual(string_schema,
                         lookup_default_string['oneOf'][0]['oneOf'][0]
                         ['properties']['default-value'])

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
            'type': Lookup.RESOURCE_SOURCE,
            'key': 'field_level_1.field_level_2',
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
            'type': Lookup.RESOURCE_SOURCE,
            'key': 'field_level_1.field_level_2',
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
            'type': Lookup.RESOURCE_SOURCE,
            'key': 'field_level_1.field_level_2',
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
            'type': Lookup.RESOURCE_SOURCE,
            'key': 'field_level_1.field_level_2'
        }

        with self.assertRaises(Exception):
            Lookup.get_value_from_resource(source, resource)
