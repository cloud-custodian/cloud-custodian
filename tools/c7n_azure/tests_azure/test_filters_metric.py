# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

from .azure_common import BaseTest
from c7n_azure.filters import MetricFilter


class MetricFilterDimensionsTest(BaseTest):

    def test_schema_accepts_dimensions(self):
        p = self.load_policy({
            'name': 'test-metric-dimensions',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'metric',
                 'metric': 'AzureOpenAIRequests',
                 'metric_namespace': 'Microsoft.CognitiveServices/accounts',
                 'op': 'lte',
                 'threshold': 0,
                 'dimensions': [
                     {'name': 'ModelDeploymentName', 'value': 'resource-name'}]}]
        }, validate=True)
        self.assertTrue(p)

    def _get_filter(self, dimensions=None):
        data = {'type': 'metric', 'metric': 'AzureOpenAIRequests', 'op': 'lte', 'threshold': 0}
        if dimensions is not None:
            data['dimensions'] = dimensions
        return MetricFilter(data=data, manager=Mock())

    def test_resolve_dimension_value_literal(self):
        f = self._get_filter()
        self.assertEqual(f.resolve_dimension_value({'name': 'anything'}, 'a-literal-value'),
                          'a-literal-value')

    def test_resolve_dimension_value_resource_name(self):
        f = self._get_filter()
        self.assertEqual(
            f.resolve_dimension_value({'name': 'my-deployment', 'id': 'ignored'},
                                       'resource-name'),
            'my-deployment')

    def test_resolve_dimension_value_resource_id(self):
        f = self._get_filter()
        self.assertEqual(
            f.resolve_dimension_value({'name': 'ignored', 'id': '/subscriptions/x'},
                                       'resource-id'),
            '/subscriptions/x')

    def test_get_resource_id_without_dimensions_uses_own_id(self):
        f = self._get_filter()
        resource = {'id': '/subscriptions/child', 'c7n:parent-id': '/subscriptions/parent'}
        self.assertEqual(f.get_resource_id(resource), '/subscriptions/child')

    def test_get_resource_id_with_dimensions_and_parent_id_uses_parent(self):
        f = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'resource-name'}])
        resource = {'id': '/subscriptions/child', 'c7n:parent-id': '/subscriptions/parent',
                    'name': 'my-deployment'}
        self.assertEqual(f.get_resource_id(resource), '/subscriptions/parent')

    def test_get_resource_id_with_dimensions_but_no_parent_id_falls_back(self):
        f = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'resource-name'}])
        resource = {'id': '/subscriptions/child', 'name': 'my-deployment'}
        self.assertEqual(f.get_resource_id(resource), '/subscriptions/child')

    def test_get_filter_without_dimensions_returns_plain_filter(self):
        f = self._get_filter()
        f.filter = "DatabaseName eq 'x'"
        self.assertEqual(f.get_filter({'id': 'x'}), "DatabaseName eq 'x'")

    def test_get_filter_with_dimensions_builds_odata_clause(self):
        f = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'resource-name'}])
        resource = {'id': '/subscriptions/child', 'name': 'my-deployment'}
        self.assertEqual(f.get_filter(resource), "ModelDeploymentName eq 'my-deployment'")

    def test_get_filter_with_dimensions_and_existing_filter_ands_together(self):
        f = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'resource-name'}])
        f.filter = "Region eq 'eastus'"
        resource = {'id': '/subscriptions/child', 'name': 'my-deployment'}
        self.assertEqual(
            f.get_filter(resource),
            "Region eq 'eastus' and ModelDeploymentName eq 'my-deployment'")

    def test_get_metrics_cache_key_differs_by_dimensions(self):
        f1 = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'dep-a'}])
        f2 = self._get_filter(dimensions=[{'name': 'ModelDeploymentName', 'value': 'dep-b'}])
        self.assertNotEqual(f1._get_metrics_cache_key(), f2._get_metrics_cache_key())


class MetricFilterPercentileTest(BaseTest):

    def test_schema_accepts_percentile(self):
        p = self.load_policy({
            'name': 'test-metric-percentile',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'metric',
                 'metric': 'Percentage CPU',
                 'aggregation': 'average',
                 'interval': 'PT1M',
                 'percentile': 95,
                 'op': 'lt',
                 'threshold': 45}]
        }, validate=True)
        self.assertTrue(p)

    def test_schema_rejects_percentile_out_of_range(self):
        for percentile in (-1, 101):
            with self.assertRaises(Exception):
                self.load_policy({
                    'name': 'test-metric-percentile-range',
                    'resource': 'azure.vm',
                    'filters': [
                        {'type': 'metric',
                         'metric': 'Percentage CPU',
                         'percentile': percentile,
                         'op': 'lt',
                         'threshold': 45}]
                }, validate=True)

    def _get_filter(self, percentile, op, threshold, **extra):
        data = {'type': 'metric', 'metric': 'Percentage CPU', 'aggregation': 'average',
                'percentile': percentile, 'op': op, 'threshold': threshold}
        data.update(extra)
        f = MetricFilter(data=data, manager=Mock())
        f.get_metric_data = Mock()
        return f

    def test_percentile_replaces_window_aggregation(self):
        # The mean of these points is 26.25, p50 is 2.5 and p99 is 96.12.
        points = [1, 2, 3, 99, None]
        f = self._get_filter(50, 'lt', 3)
        f.get_metric_data.return_value = points
        self.assertTrue(f.passes_op_filter({'id': 'vm'}))
        f = self._get_filter(99, 'lt', 75)
        f.get_metric_data.return_value = points
        self.assertFalse(f.passes_op_filter({'id': 'vm'}))

    def test_schema_accepts_percentile_bounds(self):
        for percentile in (0, 100):
            self.assertTrue(self.load_policy({
                'name': 'test-metric-percentile-bounds',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'metric',
                     'metric': 'Percentage CPU',
                     'percentile': percentile,
                     'op': 'lt',
                     'threshold': 45}]
            }, validate=True))

    def test_percentile_of_an_empty_series_with_to_zero_is_zero(self):
        f = self._get_filter(95, 'lt', 45, no_data_action='to_zero')
        f.get_metric_data.return_value = []
        self.assertTrue(f.passes_op_filter({'id': 'vm'}))
        f = self._get_filter(95, 'gt', 0, no_data_action='to_zero')
        f.get_metric_data.return_value = []
        self.assertFalse(f.passes_op_filter({'id': 'vm'}))

    def test_percentile_without_values_follows_no_data_action(self):
        for action, expected in (('exclude', False), ('include', True)):
            f = self._get_filter(95, 'lt', 45, no_data_action=action)
            f.get_metric_data.return_value = [None, None]
            self.assertEqual(f.passes_op_filter({'id': 'vm'}), expected)
