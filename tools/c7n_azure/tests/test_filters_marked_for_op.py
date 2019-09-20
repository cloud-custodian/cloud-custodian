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
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime

from mock import Mock

import tools_tags as tools
from azure_common import BaseTest
from c7n_azure.filters import TagActionFilter
from c7n_azure.utils import now
from c7n.filters.offhours import Time


class TagsTest(BaseTest):

    def test_tag_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy(filters=[
                    {'type': 'marked-for-op', 'op': 'delete', 'tag': 'custom'},
                ]), validate=True))

    def _get_filter(self, data):
        return TagActionFilter(data=data, manager=Mock)

    def _test_filter_scenario(self, resources, expected_count, filter_definition={'op': 'stop'}):
        f = self._get_filter(filter_definition)
        result = f.process(resources)
        self.assertEqual(expected_count, len(result))

    def test_tag_filter(self):
        date = now().strftime('%Y-%m-%d')
        date_future = (now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        resources = [tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date)}),
                     tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date_future)})]

        self._test_filter_scenario(resources, 1)

    def test_custom_tag_filter(self):
        date = now().strftime('%Y-%m-%d')
        resources = [tools.get_resource({'custom_status': 'TTL: stop@{0}'.format(date)})]

        filter_definition = {'op': 'stop', 'tag': 'custom_status'}

        self._test_filter_scenario(resources, 1, filter_definition)

    def test_improper_tag_format(self):
        resources = [tools.get_resource({'custodian_status': 'missingcolon}'}),
                     tools.get_resource({'custodian_status': 'missing: atsign'})]

        self._test_filter_scenario(resources, 0)

    def test_different_op_returns_no_resource(self):
        date = now().strftime('%Y-%m-%d')
        resources = [tools.get_resource({'custodian_status': 'TTL: delete@{0}'.format(date)})]

        self._test_filter_scenario(resources, 0)

    def test_misformatted_date_string(self):
        date = "notadate"
        resources = [tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date)})]

        self._test_filter_scenario(resources, 0)

    def test_timezone_in_datestring(self):
        tz = Time.get_tz('America/Santiago')
        date = (now(tz) - datetime.timedelta(hours=1)).strftime('%Y/%m/%d %H%M %Z')
        resources = [tools.get_resource({'custodian_status': 'TTL: stop@{0}'.format(date)})]

        self._test_filter_scenario(resources, 1)
