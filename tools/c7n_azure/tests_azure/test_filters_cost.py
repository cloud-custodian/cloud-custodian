# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import namedtuple

from .azure_common import BaseTest
from c7n_azure.filters import CostFilter
from c7n_azure.session import Session
from c7n_azure.utils import utcnow
from mock import Mock
import datetime

Column = namedtuple('Column', 'name')


class CostFilterTest(BaseTest):

    def setUp(self):
        super(CostFilterTest, self).setUp()
        self.session = Session()

    def test_schema(self):
        self.assertTrue(self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'cost',
                 'timeframe': 'MonthToDate',
                 'op': 'eq',
                 'value': 1}]
        }, validate=True))

        self.assertTrue(self.load_policy({
            'name': 'test-cost-filter',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'cost',
                 'timeframe': 7,
                 'op': 'eq',
                 'value': 1}]
        }, validate=True))

    def test_custom_timeframe(self):
        resources = [self._get_resource('vm1', 2000),
                     self._get_resource('vm2', 20),
                     self._get_resource('vm3', 3000)]
        f = self._get_filter({'timeframe': 'TheLastMonth', 'op': 'gt', 'value': 1000}, resources)

        result = f.process(resources, None)

        usage = f.manager.get_client.return_value.query.usage
        self._verify_expected_call(usage, 'TheLastMonth', False)
        self.assertEqual(len(result), 2)

    def test_rg(self):
        resources = [self._get_resource_group('rg1', 2000),
                     self._get_resource_group('rg2', 20),
                     self._get_resource_group('rg3', 3000)]
        f = self._get_filter({'timeframe': 1, 'op': 'lt', 'value': 1000}, resources)

        result = f.process(resources, None)

        usage = f.manager.get_client.return_value.query.usage
        self._verify_expected_call(usage, 1, True)
        self.assertEqual(len(result), 1)

    def test_child_resources(self):
        resources = [self._get_resource('vm1', 0),
                     self._get_resource('vm1/child1', 300),
                     self._get_resource('vm1/child2', 3000)]
        f = self._get_filter({'timeframe': 'WeekToDate', 'op': 'eq', 'value': 3300}, resources)

        result = f.process(resources, None)

        usage = f.manager.get_client.return_value.query.usage
        self._verify_expected_call(usage, 'WeekToDate', False)
        self.assertEqual(len(result), 1)

    def _verify_expected_call(self, mock, timeframe, resource_group):
        subscription_id = self.session.get_subscription_id()

        mock.assert_called_once()
        definition = mock.call_args[0][1]

        if isinstance(timeframe, int):
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            self.assertEqual(definition.timeframe, 'Custom')
            self.assertEqual(definition.time_period.to, today)
            self.assertEqual(definition.time_period.from_property,
                             today - datetime.timedelta(days=timeframe))
        else:
            self.assertEqual(definition.timeframe, timeframe)

        self.assertEqual(len(definition.dataset.grouping), 1)
        self.assertEqual(definition.dataset.grouping[0].type, 'Dimension')
        self.assertEqual(definition.dataset.grouping[0].name,
                         'ResourceGroupName' if resource_group else 'ResourceId')

        self.assertEqual(definition.dataset.aggregation['totalCost'].name, 'PreTaxCost')

        if not resource_group:
            self.assertEqual(definition.dataset.filter.dimension.name, 'ResourceType')
            self.assertEqual(definition.dataset.filter.dimension.operator, 'In')
            self.assertEqual(definition.dataset.filter.dimension.values,
                             ['Microsoft.Compute/virtualMachines'])

        mock.assert_called_once_with('/subscriptions/' + subscription_id, definition)

    def _get_filter(self, data, resources):
        manager = Mock()
        manager.get_session.return_value.get_subscription_id.return_value = \
            self.session.get_subscription_id()
        manager.get_client.return_value.query.usage.return_value = \
            self._get_costs(resources)
        if 'Microsoft.Compute/virtualMachines' in resources[0]['id']:
            manager.resource_type.resource_type = 'Microsoft.Compute/virtualMachines'
        else:
            manager.type = 'resourcegroup'
            manager.resource_type.resource_type = 'Microsoft.Resources/subscriptions/resourceGroups'
        return CostFilter(data=data, manager=manager)

    def _get_resource(self, name, cost):
        return {'id': '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/'
                      'TEST_VM/providers/Microsoft.Compute/virtualMachines/{0}'.format(name),
                '_cost': cost}

    def _get_resource_group(self, name, cost):
        return {'id': '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/'
                      '{0}'.format(name),
                '_cost': cost}

    def _get_costs(self, resources):
        rows = [[r['id'], r['_cost'], 'USD'] for r in resources]
        cost = {
            'columns': [
                Column('ResourceId'),
                Column('PreTaxCost'),
                Column('Currency'),
            ],
            'rows': rows
        }
        cost = namedtuple("Cost", cost.keys())(*cost.values())
        return cost
