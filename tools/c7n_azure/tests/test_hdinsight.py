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

from __future__ import absolute_import, division, print_function, unicode_literals
from azure_common import BaseTest, arm_template


class HdinsightTest(BaseTest):

    def test_hdinsight_schema_validate(self):
        p = self.load_policy({
            'name': 'test-hdinsight-schema-validate',
            'resource': 'azure.hdinsight'
        }, validate=True)
        self.assertTrue(p)

    @arm_template('hdinsight.json')
    def test_find_hdinsight_cluster_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-hdinsight-by-name',
            'resource': 'azure.hdinsight',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctesthdinsight*'
                }
            ],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
