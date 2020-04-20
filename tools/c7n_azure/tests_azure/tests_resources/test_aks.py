# Copyright 2019 Microsoft Corporation
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
from ..azure_common import BaseTest, arm_template


class AksTest(BaseTest):
    def setUp(self):
        super(AksTest, self).setUp()

    def test_aks_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-aks',
                'resource': 'azure.aks'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdnprofile.json')
    def test_find_aks_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-aks',
            'resource': 'azure.aks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestaks'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
