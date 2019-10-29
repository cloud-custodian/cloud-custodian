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

from ..azure_common import BaseTest, arm_template


class ResourceGroupTest(BaseTest):
    def setUp(self):
        super(ResourceGroupTest, self).setUp()

    def test_resource_group_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-resource-group',
                'resource': 'azure.resourcegroup',
                'filters': [
                    {'type': 'empty-group'}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('emptyrg.json')
    def test_empty_group(self):
        p = self.load_policy({
            'name': 'test-azure-resource-group',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'test_emptyrg'},
                {'type': 'empty-group'}]})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test_emptyrg')
