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

import datetime

import tools_tags as tools
from azure_common import BaseTest, arm_template
from c7n_azure.filters import TagActionFilter
from mock import Mock


class TagsTest(BaseTest):

    def test_tag_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy(filters=[
                    {'type': 'marked-for-op', 'op': 'delete', 'tag': 'custom'},
                ]), validate=True))

    def _get_filter(self, data):
        return TagActionFilter(data=data, manager=Mock)

    @arm_template('vm.json')
    def test_tag_filter(self):
        date = self.get_test_date().strftime('%Y-%m-%d')
        date_future = (self.get_test_date() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        resources = [tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date)}),
                     tools.get_resource({'custom_status': 'TTL: stop@{0}'.format(date)}),
                     tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date_future)})]

        config = [({'op': 'stop'}, 1),
                  ({'op': 'stop', 'tag': 'custom_status'}, 1)]

        for c in config:
            f = self._get_filter(c[0])
            result = f.process(resources)
            self.assertEqual(len(result), c[1])
