# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from types import SimpleNamespace

from ..azure_common import BaseTest, arm_template, cassette_name
from unittest.mock import MagicMock, patch
import requests
from c7n_azure.resources.generic_arm_resource import GenericArmResource
from c7n_azure.resources.arm import arm_tags_unsupported
from c7n.exceptions import PolicyValidationError
from c7n.testing import mock_datetime_now
from dateutil.parser import parse as date_parse


class ArmResourceTest(BaseTest):

    def setUp(self):
        super(ArmResourceTest, self).setUp()

    def test_arm_resource_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-armresource',
                'resource': 'azure.armresource'
            }, validate=True)
            self.assertTrue(p)

    def test_tag_operation_enabled(self):
        r = GenericArmResource(self.test_context, {})
        # False for excluded resources
        for t in arm_tags_unsupported:
            self.assertFalse(r.tag_operation_enabled(t))
        # Default true
        self.assertTrue(r.tag_operation_enabled("SomeResource"))

    @staticmethod
    def _mock_response(status_code, payload=None, headers=None):
        response = MagicMock()
        response.status_code = status_code
        response.headers = headers or {}
        response.json.return_value = payload or {}
        if status_code >= 400:
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                f"HTTP {status_code}")
        else:
            response.raise_for_status.return_value = None
        return response

    @patch('time.sleep')
    @patch('requests.get')
    def test_arm_rest_get_paginated_retries_and_pages(self, get_mock, sleep_mock):
        manager = GenericArmResource(self.test_context, {})
        session = MagicMock()
        session.cloud_endpoints.endpoints.resource_manager = 'https://management.azure.com/'
        session.credentials.get_token.return_value = SimpleNamespace(token='token')
        manager.get_session = MagicMock(return_value=session)

        get_mock.side_effect = [
            self._mock_response(503, headers={'retry-after': '1'}),
            self._mock_response(
                429,
                headers={'retry-after': '1'}
            ),
            self._mock_response(
                200,
                payload={'value': [{'id': '1'}], 'nextLink': 'https://next-page'}
            ),
            self._mock_response(
                200,
                payload={'value': [{'id': '2'}]}
            ),
        ]

        values = manager._arm_rest_get('https://first-page', max_retries=3)

        self.assertEqual(values, [{'id': '1'}, {'id': '2'}])
        self.assertEqual(get_mock.call_count, 4)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertEqual(get_mock.call_args_list[-1].kwargs['params'], None)

    @patch('requests.get')
    def test_arm_rest_get_paginated_non_retryable_status_raises(self, get_mock):
        manager = GenericArmResource(self.test_context, {})
        session = MagicMock()
        session.cloud_endpoints.endpoints.resource_manager = 'https://management.azure.com/'
        session.credentials.get_token.return_value = SimpleNamespace(token='token')
        manager.get_session = MagicMock(return_value=session)

        get_mock.return_value = self._mock_response(500)

        with self.assertRaises(requests.exceptions.HTTPError):
            manager._arm_rest_get('https://first-page', max_retries=3)

        self.assertEqual(get_mock.call_count, 1)

    @arm_template('vm.json')
    @cassette_name('common')
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
    def test_metric_filter_period_start_start_of_day(self):
        p = self.load_policy({
            'name': 'test-azure-metric-period-start',
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
                 'threshold': 0,
                 'period_start': 'start-of-day'}],
        })

        with mock_datetime_now(date_parse("2026-02-21T12:00:00+00:00"), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    def test_metric_filter_find(self):
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
    def test_metric_filter_find_average(self):
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
    def test_metric_filter_not_find(self):
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
    def test_metric_filter_not_find_average(self):
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

    @arm_template('vm.json')
    def test_metric_filter_invalid_metric(self):
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
                 'metric': 'InvalidMetric',
                 'aggregation': 'average',
                 'op': 'gte',
                 'threshold': 0}],
        })
        resources = p.run()
        self.assertEqual(0, len(resources))

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
        self.assertRaises(
            PolicyValidationError, self.load_policy, policy, validate=True)

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
        self.assertRaises(
            PolicyValidationError, self.load_policy, policy, validate=True)

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
        self.assertRaises(
            PolicyValidationError, self.load_policy, policy, validate=True)

    fake_arm_resources = [
        {
            'id': '/subscriptions/fake-guid/resourceGroups/test-resource-group/providers/'
                  'Microsoft.Network/networkSecurityGroups/test-nsg-delete',
            'name': 'test-nsg-delete'
        }
    ]

    @patch('c7n_azure.resources.generic_arm_resource.GenericArmResourceQuery.filter',
        return_value=fake_arm_resources)
    @patch('c7n_azure.actions.delete.DeleteAction.process',
        return_value='')
    def test_delete_armresource(self, delete_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'delete-armresource',
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
    @patch('c7n_azure.actions.delete.DeleteAction.process',
        return_value='')
    def test_delete_armresource_specific_name(self, delete_action_mock, filter_mock):
        p = self.load_policy({
            'name': 'delete-armresource',
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

    def test_arm_resource_resource_type_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-armresource-filter',
                'resource': 'azure.armresource',
                'filters': [
                    {
                        'type': 'resource-type',
                        'values': ['Microsoft.Storage/storageAccounts', 'Microsoft.Web/serverFarms']
                    }
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('vm.json')
    @cassette_name('common')
    def test_arm_resource_resource_type(self):
        p = self.load_policy({
            'name': 'test-azure-armresource-filter',
            'resource': 'azure.armresource',
            'filters': [
                {
                    'type': 'resource-type',
                    'values': [
                        'Microsoft.Network/virtualNetworks',
                        'Microsoft.Storage/storageAccounts',
                        'Microsoft.Compute/virtualMachines',
                        'resourceGroups'
                    ]
                },
                {
                    'type': 'value',
                    'key': 'resourceGroup',
                    'value_type': 'normalize',
                    'op': 'eq',
                    'value': 'test_vm'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 4)

    @arm_template('vm.json')
    def test_arm_resource_get_resources(self):
        rm = GenericArmResource(self.test_context,
                                {'policies': [
                                    {'name': 'test',
                                     'resource': 'azure.armresource'}]})

        rg_id = '/subscriptions/{0}/resourceGroups/test_vm'\
                .format(self.session.get_subscription_id())
        ids = ['{0}/providers/Microsoft.Compute/virtualMachines/cctestvm'.format(rg_id),
               rg_id]
        resources = rm.get_resources(ids)
        self.assertEqual(len(resources), 2)
        self.assertEqual({r['type'] for r in resources},
                         {'resourceGroups', 'Microsoft.Compute/virtualMachines'})
        self.assertEqual({r['id'] for r in resources},
                         set(ids))
        self.assertEqual({r['resourceGroup'] for r in resources},
                         {'test_vm'})
