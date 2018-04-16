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
from c7n_azure.session import Session
from azure_common import BaseTest

from c7n.filters import FilterValidationError


class TagsTest(BaseTest):
    """Requires at least one VM in subscription
    """
    def setUp(self):
        super(TagsTest, self).setUp()

    def test_add_single_tag_without_modifying_existing_tags(self):
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'actions': [
                {'type': 'tag',
                 'tag': 'project',
                 'value': 'contoso'}
            ],
        })
        p.run()

        # verify that the existing tags were not overridden
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        machines = list(client.virtual_machines.list_all())
        self.assertEqual(machines[0].tags, {'project': 'contoso', 'existing': 'pre-existing-tag'})

    def test_add_tags_replace_existing_tags(self):
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'actions': [
                {'type': 'tag',
                 'tags': {'tag1': 'value1', 'tag2': 222}}
            ],
        })
        p.run()

        # verify that the existing tags were overridden
        s = Session()
        client = s.client('azure.mgmt.compute.ComputeManagementClient')
        machines = list(client.virtual_machines.list_all())
        self.assertEqual(machines[0].tags, {'tag1': 'value1', 'tag2': '222'})

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
