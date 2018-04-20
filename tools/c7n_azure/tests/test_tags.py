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
from azure_common import BaseTest
from c7n_azure.session import Session
from c7n.filters import FilterValidationError


# Recorded using template: vm
class TagsTest(BaseTest):

    # latest VCR recording date that tag tests
    TEST_DATE = datetime.datetime(2018, 4, 21, 0, 0, 0)

    # regex for identifying valid email addresses
    EMAIL_REGEX = "[^@]+@[^@]+\.[^@]+"

    def setUp(self):
        super(TagsTest, self).setUp()

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