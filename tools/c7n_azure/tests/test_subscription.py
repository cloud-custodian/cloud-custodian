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

from azure_common import BaseTest


class SubscriptionTest(BaseTest):
    def setUp(self):
        super(SubscriptionTest, self).setUp()

    def test_add_policy(self):
        p = self.load_policy({
            'name': 'test-add-policy',
            'resource': 'azure.subscription',
            'filters': [
                {'type': 'missing',
                 'policy':
                     {'resource': 'azure.policyassignments',
                      'filters': [
                          {'type': 'value',
                           'key': 'properties.displayName',
                           'op': 'eq',
                           'value': 'cctestpolicydn'}]}}
            ],
            'actions': [
                {'type': 'add-policy',
                 'name': 'cctestpolicy',
                 'display_name': 'cctestpolicydn',
                 'definition_name': "Audit use of classic storage accounts"}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy({
            'name': 'test-cleanup-add-policy',
            'resource': 'azure.policyassignments',
            'filters': [
                {'type': 'value',
                 'key': 'properties.displayName',
                 'op': 'eq',
                 'value': 'cctestpolicydn'}
            ],
            'actions': [
                {'type': 'delete'}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
