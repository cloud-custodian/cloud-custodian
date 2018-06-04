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
                 'op': 'gt',
                 'func': 'avg',
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
                 'op': 'lt',
                 'func': 'avg',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)
