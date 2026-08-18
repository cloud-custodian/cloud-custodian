# Copyright 2019 Microsoft Corp
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import jsonschema

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
                         lookup_default_number['oneOf'][0]
                         ['properties']['default-value'])

        self.assertEqual(string_schema, lookup_default_string['oneOf'][1])
        self.assertEqual(string_schema,
                         lookup_default_string['oneOf'][0]
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

    def test_extract_lookup_without_key_returns_default(self):
        source = {'type': Lookup.RESOURCE_SOURCE, 'default-value': 'value_2'}
        self.assertEqual(Lookup.extract(source, {'name': 'x'}), 'value_2')

    def test_get_value_from_resource_without_key_returns_default(self):
        source = {'type': Lookup.RESOURCE_SOURCE, 'default-value': 'value_2'}
        self.assertEqual(
            Lookup.get_value_from_resource(source, {'name': 'x'}), 'value_2')

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


class LookupSchemaTest(BaseTest):
    """A lookup needs a key, a fallback, or both."""

    string_schema = {'type': 'string'}

    def validates(self, doc, schema=None):
        try:
            jsonschema.validate(doc, schema or Lookup.lookup_type(self.string_schema))
            return True
        except jsonschema.ValidationError:
            return False

    def test_key_only_accepted(self):
        self.assertTrue(self.validates({'type': 'resource', 'key': 'name'}))

    def test_key_with_default_accepted(self):
        self.assertTrue(
            self.validates(
                {'type': 'resource', 'key': 'name', 'default-value': 'x'}))

    def test_default_only_accepted(self):
        self.assertTrue(self.validates({'type': 'resource', 'default-value': 'x'}))

    def test_scalar_accepted(self):
        self.assertTrue(self.validates('plain'))

    def test_neither_key_nor_default_rejected(self):
        self.assertFalse(self.validates({'type': 'resource'}))

    def test_unknown_property_rejected(self):
        self.assertFalse(self.validates({'type': 'resource', 'ky': 'name'}))

    def test_non_lookup_dict_rejected(self):
        self.assertFalse(self.validates({'foo': 'bar'}))

    def test_default_value_is_typed_by_caller(self):
        self.assertFalse(
            self.validates({'type': 'resource', 'default-value': 5}))
        self.assertTrue(
            self.validates({'type': 'resource', 'default-value': 5},
                           Lookup.lookup_type({'type': 'number'})))

    def test_default_value_may_be_typed_separately_from_the_value(self):
        schema = Lookup.lookup_type(
            {'type': ['string', 'number']}, default_schema={'type': 'string'})
        # the bare scalar keeps the wider type
        self.assertTrue(self.validates(5, schema))
        self.assertTrue(self.validates('plain', schema))
        # the fallback is narrowed
        self.assertTrue(
            self.validates(
                {'type': 'resource', 'key': 'k', 'default-value': 'd'}, schema))
        self.assertFalse(
            self.validates(
                {'type': 'resource', 'key': 'k', 'default-value': 5}, schema))

    def test_default_schema_defaults_to_the_value_schema(self):
        one_arg = Lookup.lookup_type({'type': 'number'})
        explicit = Lookup.lookup_type(
            {'type': 'number'}, default_schema={'type': 'number'})
        self.assertEqual(one_arg, explicit)


class LookupResolveValueTest(BaseTest):

    def test_static_value_passthrough(self):
        self.assertEqual(Lookup.resolve_value('plain', {}), 'plain')

    def test_key_hit(self):
        resource = {'State': {'Name': 'running'}}
        spec = {'type': 'resource', 'key': 'State.Name'}
        self.assertEqual(Lookup.resolve_value(spec, resource), 'running')

    def test_key_miss_uses_default(self):
        spec = {'type': 'resource', 'key': 'nope', 'default-value': 'dv'}
        self.assertEqual(Lookup.resolve_value(spec, {}), 'dv')

    def test_key_miss_without_default_raises(self):
        spec = {'type': 'resource', 'key': 'nope'}
        with self.assertRaises(Exception) as cm:
            Lookup.resolve_value(spec, {})
        self.assertIn('nope', str(cm.exception))

    def test_conditional_default_writes_when_name_absent(self):
        spec = {'type': 'resource', 'default-value': 'dv'}
        self.assertEqual(
            Lookup.resolve_value(spec, {}, 'Owner', set()), 'dv')

    def test_conditional_default_skips_when_name_present(self):
        spec = {'type': 'resource', 'default-value': 'dv'}
        self.assertIs(
            Lookup.resolve_value(spec, {}, 'Owner', {'Owner'}), Lookup.SKIP)

    def test_skip_sentinel_is_distinct_from_none_and_empty_string(self):
        self.assertIsNot(Lookup.SKIP, None)
        self.assertNotEqual(Lookup.SKIP, '')


class LookupHasLookupsTest(BaseTest):

    def test_all_static(self):
        self.assertFalse(Lookup.has_lookups({'A': 'x', 'B': 'y'}))

    def test_empty(self):
        self.assertFalse(Lookup.has_lookups({}))

    def test_one_dynamic(self):
        self.assertTrue(
            Lookup.has_lookups({'A': 'x', 'B': {'type': 'resource', 'key': 'k'}}))
