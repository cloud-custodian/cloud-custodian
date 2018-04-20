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
from azure_common import arm_template


# Recorded using template: storage
class StorageTest(BaseTest):
    def setUp(self):
        super(StorageTest, self).setUp()

    @arm_template('storage.json')
    def test_value_filter(self):
        p = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

