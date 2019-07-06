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

from collections import namedtuple

import azure.mgmt.costmanagement
from azure.mgmt.costmanagement.models import QueryDefinition, QueryDataset, \
    QueryAggregation, QueryGrouping
from azure_common import BaseTest
from c7n_azure.query import DescribeSource
from c7n_azure.session import Session
from mock import patch, call

Column = namedtuple('Column', 'name')


class CostFilterTest(BaseTest):

    def setUp(self):
        super(CostFilterTest, self).setUp()
        self.session = Session()

    def test_cost_filter_schema_validate_named_timeframe(self):
        p = self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'cost',
                 'timeframe': 'MonthToDate',
                 'op': 'eq',
                 'value': 1}]
        }, validate=True)
        self.assertTrue(p)

    def test_cost_filter_schema_validate_timeframe_in_days(self):
        p = self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'cost',
                 'timeframe': 7,
                 'op': 'eq',
                 'value': 1}]
        }, validate=True)
        self.assertTrue(p)

    # run ./templates/provision.sh vm sqlserver to deploy required resource.
    def test_exact_cost(self):

        p = self.load_policy({
            'name': 'test-cost_filter',
            # 'resource': 'azure.vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'cost',
                 'timeframe': 'MonthToDate',
                 'op': 'ge',
                 'value': 0}
            ]
        })

        resources = p.run()

        self.assertTrue(len(resources) > 0)

        for resource in resources:
            self.assertEqual(resource['c7n:cost']['Currency'], 'USD')
            self.assertTrue(resource['c7n:cost']['PreTaxCost'] >= 0)

    def test_timeframe_days(self):

        p = self.load_policy({
            'name': 'test-cost_filter',
            # 'resource': 'azure.vm',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'cost',
                 'timeframe': 7,
                 'op': 'ge',
                 'value': 0}
            ]
        })

        resources = p.run()

        self.assertTrue(len(resources) > 0)

        for resource in resources:
            self.assertEqual(resource['c7n:cost']['Currency'], 'USD')
            self.assertTrue(resource['c7n:cost']['PreTaxCost'] >= 0)

    def test_cost_greater_than(self):
        p = self.load_policy({
            'name': 'test-cost_filter',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'cost',
                 'timeframe': 'TheLastWeek',
                 'op': 'gt',
                 'value': 1000}]
        })

        id1 = '/subscriptions/s1/resourceGroups/test_rg1/id1'
        id2 = '/subscriptions/s1/resourceGroups/test_rg1/id2'
        id3 = '/subscriptions/s1/resourceGroups/test_rg2/id3'
        id4 = '/subscriptions/s1/resourceGroups/test_rg2/id4'

        resources = [{'id': id1}, {'id': id2}, {'id': id3}, {'id': id4}]

        cost = self._make_cost([
            [id1, 2000],
            [id2, 20],
            [id3, 3000],
            [id4, 40],
        ])

        with patch.object(DescribeSource, 'get_resources', return_value=resources):
            with patch.object(
                    azure.mgmt.costmanagement.operations.QueryOperations,
                    'usage_by_scope',
                    return_value=cost) as mock:

                resources = p.run()

                mock.assert_has_calls([self._make_expected_call(mock, 'TheLastWeek')])

                self.assertEqual(mock.call_count, 1)

                self.assertEqual(len(resources), 2)
                self.assertEqual(resources[0]['id'], id1)
                self.assertEqual(resources[1]['id'], id3)

    def test_cost_two_filters(self):
        p = self.load_policy({
            'name': 'test-cost_filter',
            'resource': 'azure.armresource',
            'filters': [
                {'type': 'cost',
                 'timeframe': 'TheLastWeek',
                 'op': 'eq',
                 'value': 100},
                {'type': 'cost',
                 'timeframe': 'TheLastMonth',
                 'op': 'eq',
                 'value': 1000}
            ]
        })

        id1 = '/subscriptions/s1/resourceGroups/test_rg1/id1'
        id2 = '/subscriptions/s1/resourceGroups/test_rg1/id2'
        id3 = '/subscriptions/s1/resourceGroups/test_rg2/id3'
        id4 = '/subscriptions/s1/resourceGroups/test_rg2/id4'

        resources = [{'id': id1}, {'id': id2}, {'id': id3}, {'id': id4}]

        week_cost = self._make_cost([
            [id1, 100],
            [id2, 100],
            [id3, 100],
            [id4, 10],
        ])

        month_cost = self._make_cost([
            [id1, 2000],
            [id2, 1000],
            [id3, 1000],
            [id4, 1000],
        ])

        with patch.object(DescribeSource, 'get_resources', return_value=resources):
            with patch.object(
                    azure.mgmt.costmanagement.operations.QueryOperations,
                    'usage_by_scope') as mock:

                mock.side_effect = [week_cost, month_cost]

                resources = p.run()

                mock.assert_has_calls([
                    self._make_expected_call(mock, 'TheLastWeek'),
                    self._make_expected_call(mock, 'TheLastMonth')])

                self.assertEqual(mock.call_count, 2)

                self.assertEqual(len(resources), 2)
                self.assertEqual(resources[0]['id'], id2)
                self.assertEqual(resources[1]['id'], id3)

    def _make_expected_call(self, mock, timeframe):
        grouping = [QueryGrouping(type='Dimension', name='ResourceId')]
        aggregation = {'totalCost': QueryAggregation(name='PreTaxCost')}
        dataset = QueryDataset(grouping=grouping, aggregation=aggregation)
        definition = QueryDefinition(timeframe=timeframe, dataset=dataset)
        subscription_id = self.session.get_subscription_id()
        return call('/subscriptions/' + subscription_id, definition)

    def _make_cost(self, rows):
        cost = {
            'columns': [
                Column('ResourceId'),
                Column('PreTaxCost'),
                Column('Currency'),
            ],
            'rows': rows
        }

        cost = namedtuple("Cost", cost.keys())(*cost.values())

        return [cost]
