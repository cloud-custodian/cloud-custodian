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

from . import tools_tags as tools
from .azure_common import BaseTest, arm_template
from mock import Mock

from c7n.filters.core import ValueFilter


class TagsTest(BaseTest):

    def test_tag_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy(filters=[
                    {'tag:Test': 'value'},
                ]), validate=True))

    def _get_filter(self, data):
        return ValueFilter(data=data, manager=Mock)

    @arm_template('vm.json')
    def test_tag_filter(self):

        resources = [tools.get_resource({'Pythontest': 'ItWorks', 'Another-Tag-1': 'value1'})]

        config = [({'tag:Pythontest': 'present'}, 1),
                  ({'tag:Pythontest': 'absent'}, 0),
                  ({'tag:Pythontest': 'ItWorks'}, 1),
                  ({'tag:Pythontest': 'ItDoesntWork'}, 0)]

        for c in config:
            f = self._get_filter(c[0])
            result = f.process(resources)
            self.assertEqual(len(result), c[1])
