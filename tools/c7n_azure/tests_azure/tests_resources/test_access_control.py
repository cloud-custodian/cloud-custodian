# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, strict_cassette
from azure.core.exceptions import HttpResponseError
from c7n_azure.resources.access_control import DeleteRoleDefinitionAction, ScopeFilter
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
                'resource': 'azure.roledefinition',
                'actions': [
                    {'type': 'delete'}
                ]
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

    def test_delete_role_definition_get_scope(self):
        role = "/providers/Microsoft.Authorization/roleDefinitions/foo"
        sub_scope = "/subscriptions/111-111-1111"
        resource_group_scope = sub_scope + "/resourceGroups/foo"
        management_group_scope = "/providers/Microsoft.Management/managementGroups/foo"

        get_scope = DeleteRoleDefinitionAction.get_scope

        self.assertEqual(get_scope(sub_scope + role), sub_scope)
        self.assertEqual(get_scope(resource_group_scope + role), resource_group_scope)
        self.assertEqual(get_scope(management_group_scope + role), management_group_scope)
        self.assertEqual(get_scope(sub_scope + role.lower()), sub_scope)
        with self.assertRaises(ValueError):
            get_scope(role)

    @arm_template('roledefinition-delete.json')
    @strict_cassette('roledefinition-delete')
    def test_delete_role_definition(self):
        p = self.load_policy({
            'name': 'test-delete-role-definition',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'value': 'cctest-roledefinition-delete'}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        self.sleep_in_live_mode(30)
        client = p.resource_manager.get_client()
        remaining = client.role_definitions.list(
            '/subscriptions/%s' % self.session.get_subscription_id(),
            filter="roleName eq 'cctest-roledefinition-delete'")
        self.assertEqual(list(remaining), [])

    @strict_cassette('roledefinition-delete-skips-built-in')
    def test_delete_role_definition_skips_built_in(self):
        p = self.load_policy({
            'name': 'test-delete-built-in-role-definition',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'value': 'Reader'}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        with self.assertLogs('custodian.azure.AzureBaseAction', level='WARNING') as logs:
            resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['properties']['type'], 'BuiltInRole')
        self.assertEqual(logs.output, [
            'WARNING:custodian.azure.AzureBaseAction:delete implicitly filtered '
            '0 of 1 resources key:properties.type on CustomRole'])

    @arm_template('roledefinition-delete-assigned.json')
    @strict_cassette('roledefinition-delete-assigned')
    def test_delete_role_definition_with_assignments(self):
        p = self.load_policy({
            'name': 'test-delete-assigned-role-definition',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'value': 'cctest-roledefinition-delete-assigned'}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        with self.assertRaises(HttpResponseError) as e:
            p.run()

        self.assertEqual(e.exception.error.code, 'RoleDefinitionHasAssignments')

    @strict_cassette('roledefinition-delete-already-deleted')
    def test_delete_role_definition_already_deleted(self):
        p = self.load_policy({
            'name': 'test-delete-deleted-role-definition',
            'resource': 'azure.roledefinition',
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        # The role test_delete_role_definition deletes, which Azure answers with 204
        role_id = '00000000-0000-0000-0000-000000000010'
        role = {
            'id': '/subscriptions/%s/providers/Microsoft.Authorization/roleDefinitions/%s' % (
                self.session.get_subscription_id(), role_id),
            'name': role_id,
            'properties': {'roleName': 'cctest-roledefinition-delete'},
        }
        action = p.resource_manager.actions[0]
        action._prepare_processing()

        self.assertEqual(
            action._process_resource(role),
            "role 'cctest-roledefinition-delete' already deleted")
