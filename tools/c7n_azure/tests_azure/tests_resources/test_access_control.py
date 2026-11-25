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
            f'/subscriptions/{self.session.get_subscription_id()}',
            filter="roleName eq 'cctest-roledefinition-delete'")
        self.assertEqual(list(remaining), [])

    # Setup: tofu apply in terraform/roledefinition_management_group (read its header)
    @strict_cassette('roledefinition-delete-management-group')
    def test_delete_role_definition_from_management_group(self):
        group_scope = '/providers/Microsoft.Management/managementGroups/cctest-roledefinition-mg'
        p = self.load_policy({
            'name': 'test-delete-management-group-role-definition',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'value': 'cctest-roledefinition-mg'}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn(
            group_scope.lower(),
            [s.lower() for s in resources[0]['properties']['assignableScopes']])

        # Gone where c7n found it, and where it was created.
        self.sleep_in_live_mode(30)
        client = p.resource_manager.get_client()
        for scope in (f'/subscriptions/{self.session.get_subscription_id()}', group_scope):
            remaining = client.role_definitions.list(
                scope, filter="roleName eq 'cctest-roledefinition-mg'")
            self.assertEqual(list(remaining), [], scope)

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

    @strict_cassette('roledefinition-delete-already-deleted')
    def test_delete_role_definition_already_deleted(self):
        p = self.load_policy({
            'name': 'test-delete-deleted-role-definition',
            'resource': 'azure.roledefinition',
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        # A role id that doesn't exist; Azure answers 204
        role_id = '00000000-0000-0000-0000-000000000010'
        subscription_id = self.session.get_subscription_id()
        role = {
            'id': (f'/subscriptions/{subscription_id}'
                   f'/providers/Microsoft.Authorization/roleDefinitions/{role_id}'),
            'name': role_id,
            'properties': {'roleName': 'cctest-roledefinition-delete'},
        }
        action = p.resource_manager.actions[0]
        action._prepare_processing()

        self.assertEqual(
            action._process_resource(role),
            "role 'cctest-roledefinition-delete' already deleted")

    @arm_template('roledefinition-delete.json')
    @arm_template('roledefinition-delete-assigned.json')
    @strict_cassette('roledefinition-delete-continues')
    def test_delete_role_definition_continues_after_failure(self):
        p = self.load_policy({
            'name': 'test-delete-role-definitions',
            'resource': 'azure.roledefinition',
            'filters': [
                {'type': 'value',
                 'key': 'properties.roleName',
                 'op': 'in',
                 'value': ['cctest-roledefinition-delete',
                           'cctest-roledefinition-delete-assigned']}],
            'actions': [
                {'type': 'delete'}
            ]
        }, validate=True)
        # The assigned role fails, so put it first to show the other is still deleted
        resources = sorted(
            p.resource_manager.resources(),
            key=lambda r: r['properties']['roleName'], reverse=True)
        self.assertEqual(
            [r['properties']['roleName'] for r in resources],
            ['cctest-roledefinition-delete-assigned', 'cctest-roledefinition-delete'])

        with self.assertRaises(HttpResponseError) as e:
            p.resource_manager.actions[0].process(resources)
        self.assertEqual(e.exception.error.code, 'RoleDefinitionHasAssignments')

        self.sleep_in_live_mode(30)
        client = p.resource_manager.get_client()
        scope = f'/subscriptions/{self.session.get_subscription_id()}'
        deleted = client.role_definitions.list(
            scope, filter="roleName eq 'cctest-roledefinition-delete'")
        assigned = client.role_definitions.list(
            scope, filter="roleName eq 'cctest-roledefinition-delete-assigned'")
        self.assertEqual(list(deleted), [])
        self.assertEqual(len(list(assigned)), 1)
