# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template
from c7n_azure.resources.access_control import ScopeFilter
from unittest.mock import patch, MagicMock


class AccessControlTest(BaseTest):
    def setUp(self):
        super(AccessControlTest, self).setUp()

    def test_validate_role_assignments_schema(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-assignments-by-role',
                'resource': 'azure.roleassignment',
                'filters': [
                    {'type': 'role',
                     'key': 'properties.roleName',
                     'op': 'eq',
                     'value': 'Owner'},
                    {'type': 'resource-access',
                     'relatedResource': 'azure.vm'},
                    {'type': 'scope',
                     'value': 'subscription'}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            }, validate=True)

            self.assertTrue(p)

    def test_validate_role_definitions_schema(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-assignments-by-role',
                'resource': 'azure.roledefinition'
            }, validate=True)

            self.assertTrue(p)

    @patch('c7n_azure.resources.access_control.RoleAssignment.augment')
    def test_find_assignments_by_role(self, mock_augment):
        def mock_return_resources(args):
            return args
        mock_augment.side_effect = mock_return_resources
        p = self.load_policy({
            'name': 'test-assignments-by-role',
            'resource': 'azure.roleassignment',
            'filters': [
                {'type': 'role',
                 'key': 'properties.roleName',
                 'op': 'eq',
                 'value': 'Owner'}],
        })
        resources = p.run()
        self.assertTrue(len(resources) > 0)

    @arm_template('vm.json')
    @patch('c7n_azure.resources.access_control.RoleAssignment.augment')
    def test_find_assignments_by_resources(self, mock_augment):
        def mock_return_resources(args):
            return args
        mock_augment.side_effect = mock_return_resources
        p = self.load_policy({
            'name': 'test-assignments-by-role',
            'resource': 'azure.roleassignment',
            'filters': [
                {'type': 'resource-access',
                 'relatedResource': 'azure.vm'}],
        })
        resources = p.run()
        self.assertTrue(len(resources) > 0)

    def test_find_definition_by_name(self):
        p = self.load_policy({
            'name': 'test-roledefinition-by-name',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'op': 'eq',
                 'value': 'Owner'}],
        })
        definitions = p.run()
        self.assertEqual(len(definitions), 1)

    def test_scope_filter_subscription(self):
        sub_scope = "/subscriptions/111-111-1111"
        resource_group_scope = sub_scope + "/resourceGroups/foo"
        management_group_scope = "/providers/Microsoft.Management/managementGroups/foo"

        scope_filter = ScopeFilter(MagicMock())

        sub_type = 'subscription'
        self.assertTrue(scope_filter.is_scope(sub_scope, sub_type))
        self.assertFalse(scope_filter.is_scope(resource_group_scope, sub_type))
        self.assertFalse(scope_filter.is_scope(management_group_scope, sub_type))
        self.assertFalse(scope_filter.is_scope("subscriptions", sub_type))
        self.assertFalse(scope_filter.is_scope("/subscription", sub_type))
        self.assertFalse(scope_filter.is_scope("/foo/bar", sub_type))

    def test_scope_filter_resource_group(self):
        sub_scope = "/subscriptions/111-111-1111"
        resource_group_scope = sub_scope + "/resourceGroups/foo"
        management_group_scope = "/providers/Microsoft.Management/managementGroups/foo"

        scope_filter = ScopeFilter(MagicMock())

        rg_type = 'resource-group'

        self.assertTrue(scope_filter.is_scope(resource_group_scope, rg_type))
        self.assertFalse(scope_filter.is_scope(sub_scope, rg_type))
        self.assertFalse(scope_filter.is_scope(management_group_scope, rg_type))
        self.assertFalse(scope_filter.is_scope("/subscriptions/resourceGroups", rg_type))
        self.assertFalse(scope_filter.is_scope("/subscriptions/resourceGroups/", rg_type))
        self.assertFalse(scope_filter.is_scope("/subscriptions/resourceGroup/", rg_type))
        self.assertFalse(scope_filter.is_scope("/subscription/resourceGroups/foo", rg_type))
        self.assertFalse(scope_filter.is_scope("/foo/bar/xyz", rg_type))
        self.assertFalse(scope_filter.is_scope(resource_group_scope + "/vm/bar", rg_type))

    def test_scope_filter_management_group(self):
        sub_scope = "/subscriptions/111-111-1111"
        resource_group_scope = sub_scope + "/resourceGroups/foo"
        management_group_scope = "/providers/Microsoft.Management/managementGroups/foo"

        scope_filter = ScopeFilter(MagicMock())

        mg_type = 'management-group'

        self.assertTrue(scope_filter.is_scope(management_group_scope, mg_type))
        self.assertFalse(scope_filter.is_scope(resource_group_scope, mg_type))
        self.assertFalse(scope_filter.is_scope(sub_scope, mg_type))
