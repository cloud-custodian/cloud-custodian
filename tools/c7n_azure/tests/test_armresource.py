# Copyright 2015-2018 Capital One Services, LLC
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

from azure_common import BaseTest, arm_template
from datetime import datetime
from mock import patch
from jsonschema.exceptions import ValidationError


class ArmResourceTest(BaseTest):

    TEST_DATE = datetime(2018, 6, 1, 0, 0, 0)

    def setUp(self):
        super(ArmResourceTest, self).setUp()

    @arm_template('vm.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-armresource',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_filter_find(self, utcnow_mock):
        p = self.load_policy({
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Network In',
                 'aggregation': 'total',
                 'op': 'gt',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_filter_find_average(self, utcnow_mock):
        p = self.load_policy({
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Percentage CPU',
                 'aggregation': 'average',
                 'op': 'gt',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_filter_not_find(self, utcnow_mock):
        p = self.load_policy({
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Network In',
                 'aggregation': 'total',
                 'op': 'lt',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @arm_template('vm.json')
    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_metric_filter_not_find_average(self, utcnow_mock):
        p = self.load_policy({
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Percentage CPU',
                 'aggregation': 'average',
                 'op': 'lt',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_metric_filter_invalid_missing_metric(self):
        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'aggregation': 'total',
                 'op': 'lt',
                 'threshold': 0}],
        }
        self.assertRaises(ValidationError, self.load_policy, policy, validate=True)

    def test_metric_filter_invalid_missing_op(self):
        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Network In',
                 'aggregation': 'total',
                 'threshold': 0}],
        }
        self.assertRaises(ValidationError, self.load_policy, policy, validate=True)

    def test_metric_filter_invalid_missing_threshold(self):
        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'metric',
                 'metric': 'Network In',
                 'aggregation': 'total',
                 'op': 'lt'}],
        }
        self.assertRaises(ValidationError, self.load_policy, policy, validate=True)

    fake_arm_resources = [
        {
            'id': '/subscriptions/fake-guid/resourceGroups/test-resource-group/providers/'
                  'Microsoft.Network/networkSecurityGroups/test-nsg-delete',
            'name': 'test-nsg-delete'
        }
    ]

    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_arm_resources)
    @patch('c7n_azure.actions.DeleteAction.process',
        return_value='')
    def test_delete_armresource(self, delete_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'delete-arm-resource',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test-nsg-delete'}],
            'actions': [
                {'type': 'delete'}
            ]
        })
        p.run()
        delete_action_mock.assert_called_with([self.fake_arm_resources[0]])

    @patch('c7n_azure.query.ResourceQuery.filter',
        return_value=fake_arm_resources)
    @patch('c7n_azure.actions.DeleteAction.process',
        return_value='')
    def test_delete_armresource_specific_name(self, delete_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'delete-arm-resource',
            'resource': 'azure.networksecuritygroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test-nsg-delete'}],
            'actions': [
                {'type': 'delete'}
            ]
        })
        p.run()
        delete_action_mock.assert_called_with([self.fake_arm_resources[0]])
