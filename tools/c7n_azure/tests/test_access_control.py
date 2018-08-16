# Copyright 2015-2018 Capital One Services, LLC
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
from mock import patch
from c7n_azure.resources.access_control import is_scope


class AccessControlTest(BaseTest):
    def setUp(self):
        super(AccessControlTest, self).setUp()

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

    def test_is_scope(self):
        sub_scope = "/subscriptions/111-111-1111"
        resource_group_scope = sub_scope + "/resourceGroups/foo"

        # Subscription scope tests
        self.assertTrue(is_scope(sub_scope, "subscription"))
        self.assertFalse(is_scope(resource_group_scope, "subscription"))
        self.assertFalse(is_scope("subscriptions", "subscription"))
        self.assertFalse(is_scope("/subscription", "subscription"))
        self.assertFalse(is_scope("/foo/bar", "subscription"))

        # Resource group scope test
        self.assertTrue(is_scope(resource_group_scope, "resource-group"))
        self.assertFalse(is_scope(sub_scope, "resource-group"))
        self.assertFalse(is_scope("/subscriptions/resourceGroups", "resource-group"))
        self.assertFalse(is_scope("/subscriptions/resourceGroups/", "resource-group"))
        self.assertFalse(is_scope("/subscriptions/resourceGroup/", "resource-group"))
        self.assertFalse(is_scope("/subscription/resourceGroups/foo", "resource-group"))
        self.assertFalse(is_scope("/foo/bar/xyz", "resource-group"))
