# Copyright 2015-2019 Microsoft Corporation
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


class CostFilterTest(BaseTest):

    @arm_template('vm.json')
    def test_cost_resource(self):

        p = self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'type': 'cost',
                 'timeframe': 1,
                 'op': 'ge',
                 'value': 0}
            ]
        })

        resources = p.run()

        self.assertTrue(len(resources) > 0)

        for resource in resources:
            self.assertEqual(resource['c7n:cost']['Currency'], 'USD')
            self.assertTrue(resource['c7n:cost']['PreTaxCost'] >= 0)

    @arm_template('vm.json')
    def test_cost_resource_group(self):

        p = self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'},
                {'type': 'cost',
                 'timeframe': 1,
                 'op': 'ge',
                 'value': 0}
            ]
        })

        resources = p.run()

        self.assertTrue(len(resources) > 0)

        for resource in resources:
            self.assertEqual(resource['c7n:cost']['Currency'], 'USD')
            self.assertTrue(resource['c7n:cost']['PreTaxCost'] >= 0)
