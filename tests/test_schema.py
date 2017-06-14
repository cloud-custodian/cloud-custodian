# Copyright 2016 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import mock
from json import dumps
from jsonschema.exceptions import best_match

from c7n.manager import resources
from c7n.schema import Validator, validate, generate, specific_error
from .common import BaseTest


class SchemaTest(BaseTest):

    validator = None

    def findError(self, data, validator):
        e = best_match(validator.iter_errors(data))
        ex = specific_error(list(validator.iter_errors(data))[0])
        return e, ex

    def setUp(self):
        if not self.validator:
            self.validator = Validator(generate())

    def test_schema_plugin_name_mismatch(self):
        for k, v in resources.items():
            for fname, f in v.filter_registry.items():
                if fname in ('or', 'and', 'not'):
                    continue
                self.assertIn(
                    fname, f.schema['properties']['type']['enum'])
            for aname, a in v.action_registry.items():
                self.assertIn(
                    aname, a.schema['properties']['type']['enum'])

    def test_schema(self):
        try:
            schema = generate()
            Validator.check_schema(schema)
        except Exception:
            self.fail("Invalid schema")

    def test_schema_serialization(self):
        try:
            dumps(generate())
        except:
            self.fail("Failed to serialize schema")

    def test_empty_skeleton(self):
        self.assertEqual(validate({'policies': []}), [])

    def test_duplicate_policies(self):
        data = {
            'policies': [
                {'name': 'monday-morning',
                 'resource': 'ec2'},
                {'name': 'monday-morning',
                 'resource': 'ec2'},
                ]}

        result = validate(data)
        self.assertEqual(len(result), 1)
        self.assertTrue(isinstance(result[0], ValueError))
        self.assertTrue('monday-morning' in str(result[0]))

    def test_semantic_error(self):
        data = {
            'policies': [
                {'name': 'test',
                 'resource': 'ec2',
                 'filters': {
                     'type': 'ebs',
                     'skipped_devices': []}
                    }]
            }
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(len(errors), 1)
        error = specific_error(errors[0])
        self.assertTrue(
            len(errors[0].absolute_schema_path) < len(
                error.absolute_schema_path))

        self.assertTrue(
            "u'skipped_devices': []" in error.message)
        self.assertTrue(
            "u'type': u'ebs'" in error.message)

    @mock.patch('c7n.schema.specific_error')
    def test_handle_specific_error_fail(self, mock_specific_error):
        from jsonschema.exceptions import ValidationError
        data = {
                'policies': [{'name': 'test',
                 'resource': 'ec2',
                 'filters': {
                     'type': 'ebs',
                     'invalid': []}
                    }]
            }
        mock_specific_error.side_effect = ValueError('The specific error crapped out hard')
        resp = validate(data)
        # if it is 2, then we know we got the exception from specific_error
        self.assertEqual(len(resp), 2)
        self.assertIsInstance(resp[0], ValidationError)
        self.assertIsInstance(resp[1], ValidationError)


    def test_vars_and_tags(self):
        data = {
            'vars': {'alpha': 1, 'beta': 2},
            'policies': [{
                'name': 'test',
                'resource': 'ec2',
                'tags': ['controls']}]}
        self.assertEqual(list(self.validator.iter_errors(data)), [])

    def test_semantic_error_on_value_derived(self):
        data = {
            'policies': [
                {'name': 'test',
                 'resource': 'ec2',
                 'filters': [
                     {'type': 'ebs',
                      'skipped_devices': []}
                     ]}
            ]}
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(len(errors), 1)
        error = specific_error(errors[0])
        self.assertTrue(
            len(errors[0].absolute_schema_path) < len(
                error.absolute_schema_path))
        self.assertEqual(
            error.message,
            ("Additional properties are not allowed "
             "(u'skipped_devices' was unexpected)"))

    def test_invalid_resource_type(self):
        data = {
            'policies': [
                {'name': 'instance-policy',
                 'resource': 'ec3',
                 'filters': []}]}
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(len(errors), 1)

    def test_value_filter_short_form_invalid(self):
        for rtype in ["elb", "rds", "ec2"]:
            data = {
                'policies': [
                    {'name': 'instance-policy',
                     'resource': 'elb',
                     'filters': [
                         {"tag:Role": "webserver"}]}
                ]}
            schema = generate([rtype])
            # Disable standard value short form
            schema['definitions']['filters']['valuekv'] = {'type': 'number'}
            validator = Validator(schema)
            errors = list(validator.iter_errors(data))
            self.assertEqual(len(errors), 1)

    def test_nested_bool_operators(self):
        data = {
            'policies': [
                {'name': 'test',
                 'resource': 'ec2',
                 'filters': [
                     {'or': [
                         {'tag:Role': 'webserver'},
                         {'type': 'value', 'key': 'x', 'value': []},
                         {'and': [
                             {'tag:Name': 'cattle'},
                             {'tag:Env': 'prod'}]
                          }]
                      }]
                 }]
            }
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(errors, [])

    def test_value_filter_short_form(self):
        data = {
            'policies': [
                {'name': 'instance-policy',
                 'resource': 'elb',
                 'filters': [
                     {"tag:Role": "webserver"}]}
                ]}

        errors = list(self.validator.iter_errors(data))
        self.assertEqual(errors, [])

    def test_event_inherited_value_filter(self):
        data = {
            'policies': [
                {'name': 'test',
                 'resource': 'ec2',
                 'filters': [
                     {'type': 'event',
                      'key': "detail.requestParameters",
                      "value": "absent"}]}]
            }
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(errors, [])

    def test_ebs_inherited_value_filter(self):
        data = {
            'policies': [
                {'name': 'test',
                 'resource': 'ec2',
                 'filters': [
                     {'type': 'ebs',
                      'key': 'Encrypted',
                      'value': False,
                      'skip-devices': [
                          '/dev/sda1',
                          '/dev/xvda']}
                     ]}
                ]}
        errors = list(self.validator.iter_errors(data))
        self.assertEqual(errors, [])

    def test_offhours_stop(self):
        data = {
            'policies': [
                {'name': 'ec2-offhours-stop',
                 'resource': 'ec2',
                 'filters': [
                     {'tag:aws:autoscaling:groupName': 'absent'},
                     {'type': 'offhour',
                      'tag': 'c7n_downtime',
                      'default_tz': 'et',
                      'offhour': 19}]
                 }]
            }
        schema = generate(['ec2'])
        validator = Validator(schema)
        errors = list(validator.iter_errors(data))
        self.assertEqual(len(errors), 0)

    def test_instance_age(self):
        data = {
            'policies': [
                {'name': 'ancient-instances',
                 'resource': 'ec2',
                 'query': [{'instance-state-name': 'running'}],
                 'filters': [{'days': 60, 'type': 'instance-age'}]
             }]}
        schema = generate(['ec2'])
        validator = Validator(schema)
        errors = list(validator.iter_errors(data))
        self.assertEqual(len(errors), 0)

    def test_mark_for_op(self):
        data = {
            'policies': [{
                'name': 'ebs-mark-delete',
                'resource': 'ebs',
                'filters': [],
                'actions': [{
                    'type': 'mark-for-op',
                    'op': 'delete',
                    'days': 30}]}]
            }
        schema = generate(['ebs'])
        validator = Validator(schema)

        errors = list(validator.iter_errors(data))
        self.assertEqual(len(errors), 0)

