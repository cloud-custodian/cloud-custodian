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
import datetime
import re
from mock import patch
from c7n_azure.session import Session
from c7n.filters import FilterValidationError
from azure_common import BaseTest, arm_template


class TagsTest(BaseTest):

    # latest VCR recording date that tag tests
    TEST_DATE = datetime.datetime(2018, 4, 21, 0, 0, 0)

    # regex for identifying valid email addresses
    EMAIL_REGEX = "[^@]+@[^@]+\.[^@]+"

    def setUp(self):
        super(TagsTest, self).setUp()

    @arm_template('vm.json')
    def test_add_or_update_single_tag(self):
        """Verifies we can add a new tag to a VM and not modify
        an existing tag on that resource
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tag': 'tag1',
                 'value': 'value1'}
            ],
        })
        p.run()

        # verify that the a new tag is added without modifying existing tags
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        vm = client.virtual_machines.get('test_vm', 'cctestvm')
        self.assertEqual(vm.tags, {'tag1': 'value1', 'testtag': 'testvalue'})

    @arm_template('vm.json')
    def test_add_or_update_tags(self):
        """Adds tags to an empty resource group, then updates one
        tag and adds a new tag
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}},
            ],
        })
        p.run()

        # verify initial tag set
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertEqual(rg.tags,
                         {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'})

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'tag1': 'value1', 'pre-existing-1': 'modified'}}
            ],
        })
        p.run()

        # verify modified tags
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertEqual(rg.tags,
                         {'tag1': 'value1', 'pre-existing-1': 'modified', 'pre-existing-2': 'unmodified'})

    def test_cant_have_both_tag_and_tags(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tags': {'tag2': 'value2'},
                     'tag': 'tag1',
                     'value': 'value1'}
                ],
            })
            p.run()

    def test_must_specify_tags_or_tag_and_value(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag'}
                ],
            })
            p.run()

    def test_must_specify_non_empty_tags(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tags': {}}
                ],
            })
            p.run()

    def test_must_specify_both_tag_and_value(self):
        with self.assertRaises(FilterValidationError):
            # Missing value
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tag': 'myTag'}
                ],
            })
            p.run()

            # Missing tag
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'value': 'myValue'}
                ],
            })
            p.run()

    @arm_template('vm.json')
    def test_remove_single_tag(self):
        """Verifies we can delete a tag to a VM and not modify
        an existing tag on that resource
        """
        p = self.load_policy({
            'name': 'test-azure-remove-single-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tag': 'tag1',
                 'value': 'to-delete'}
            ],
        })
        p.run()

        # verify the initial tag set
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        vm = client.virtual_machines.get('test_vm', 'cctestvm')
        self.assertEqual(vm.tags, {'tag1': 'to-delete', 'testtag': 'testvalue'})

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['tag1']}
            ],
        })
        p.run()

        # verify that the a tag is deleted without modifying existing tags
        vm = client.virtual_machines.get('test_vm', 'cctestvm')
        self.assertEqual(vm.tags, {'testtag': 'testvalue'})

    @arm_template('vm.json')
    def test_remove_tags(self):
        """Verifies we can delete multiple tags from a resource
        group without modifying existing tags.
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'pre-existing-1': 'to-keep', 'pre-existing-2': 'to-keep',
                          'added-1': 'to-delete', 'added-2': 'to-delete'}},
            ],
        })
        p.run()

        # verify initial tag set
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertEqual(rg.tags,
                         {'pre-existing-1': 'to-keep', 'pre-existing-2': 'to-keep',
                          'added-1': 'to-delete', 'added-2': 'to-delete'})

        p = self.load_policy({
            'name': 'test-azure-remove-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['added-1', 'added-2']}
            ],
        })
        p.run()

        # verify tags removed and pre-existing tags not removed
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertEqual(rg.tags,
                         {'pre-existing-1': 'to-keep', 'pre-existing-2': 'to-keep'})

    @arm_template('vm.json')
    def test_removal_does_not_raise_on_nonexistent_tag(self):
        """Verifies attempting to delete a tag that is
        not on the resource does not throw an error
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['tag-does-not-exist']},
            ],
        })

        # verify initial tag set is empty
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        vm = client.virtual_machines.get('test_vm', 'cctestvm')
        self.assertEqual(vm.tags, {'testtag': 'testvalue'})

        raised = False
        try:
            p.run()
        except KeyError:
            raised = True

        # verify no exception raised and no changes to tags on resource
        self.assertFalse(raised)
        self.assertEqual(vm.tags, {'testtag': 'testvalue'})

    def test_must_specify_tags_to_remove(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'untag'}
                ],
            })
            p.run()

    @arm_template('vm.json')
    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    def test_auto_tag_add_creator_tag(self, utcnow_mock):
        """Adds CreatorEmail to a resource group
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'auto-tag-user',
                 'tag': 'CreatorEmail'},
            ],
        })
        p.run()

        # verify CreatorEmail tag set
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertTrue(re.match(self.EMAIL_REGEX, rg.tags['CreatorEmail']))

    @patch('c7n_azure.actions.utcnow', return_value=TEST_DATE)
    @arm_template('vm.json')
    def test_auto_tag_update_false_noop_for_existing_tag(self, utcnow_mock):
        """Adds CreatorEmail to a resource group
        """

        # setup by adding an existing CreatorEmail tag
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tag': 'CreatorEmail',
                 'value': 'do-not-modify'},
            ],
        })
        p.run()

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'test_vm'}
            ],
            'actions': [
                {'type': 'auto-tag-user',
                 'tag': 'CreatorEmail',
                 'update': False,
                 'days': 10}
            ],
        })
        p.run()

        # verify CreatorEmail tag was not modified
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        rg = [rg for rg in client.resource_groups.list() if rg.name == 'test_vm'][0]
        self.assertEqual(rg.tags['CreatorEmail'], 'do-not-modify')

    def test_auto_tag_days_must_be_btwn_1_and_90(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 91}
                ],
            })
            p.run()

        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 0}
                ],
            })
            p.run()