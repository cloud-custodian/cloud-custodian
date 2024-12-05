# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from .azure_common import BaseTest, arm_template


class CostFilterTest(BaseTest):

    @arm_template('vm.json')
    @pytest.mark.skiplive
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
                 'timeframe': 30,
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
    @pytest.mark.skiplive
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
                 'timeframe': 30,
                 'op': 'ge',
                 'value': 0}
            ]
        })

        resources = p.run()

        self.assertTrue(len(resources) > 0)

        for resource in resources:
            self.assertEqual(resource['c7n:cost']['Currency'], 'USD')
            self.assertTrue(resource['c7n:cost']['PreTaxCost'] >= 0)
