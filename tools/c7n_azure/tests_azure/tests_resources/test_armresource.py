# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, cassette_name
from unittest.mock import patch
from c7n_azure.resources.generic_arm_resource import GenericArmResource
from c7n_azure.resources.arm import arm_tags_unsupported
from c7n.exceptions import PolicyValidationError


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
    def test_metric_filter_start_of_day(self):
        p = self.load_policy({
            'name': 'test-azure-metric-sod',
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
                 'start-of-day': True}],
        })
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
