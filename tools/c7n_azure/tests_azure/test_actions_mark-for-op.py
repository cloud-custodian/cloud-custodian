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

from c7n_azure import utils
from c7n_azure.actions.tagging import TagDelayedAction
from mock import patch, Mock

from . import tools_tags as tools
from .azure_common import BaseTest


class ActionsMarkForOpTest(BaseTest):

    existing_tags = {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}
    DAYS = 10

    def _get_action(self, data):
        return TagDelayedAction(data=data, manager=Mock())

    def test_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy([
                    {'type': 'mark-for-op',
                     'op': 'delete',
                     'days': 10},
                ]),
                validate=True))

    @patch('c7n_azure.tags.TagHelper.update_resource_tags')
    def test_mark_for_op(self, update_resource_tags):
        self.patch(TagDelayedAction, 'type', 'mark-for-op')
        action = self._get_action({'op': 'stop', 'days': self.DAYS})
        resource = tools.get_resource(self.existing_tags)

        action.process([resource])

        tags = tools.get_tags_parameter(update_resource_tags)

        date = (utils.now(tz=action.tz) + datetime.timedelta(days=self.DAYS)).strftime('%Y/%m/%d')
        expected_value = TagDelayedAction.default_template.format(op='stop', action_date=date)
        expected_tags = self.existing_tags.copy()
        expected_tags.update({'custodian_status': expected_value})

        self.assertEqual(tags, expected_tags)
