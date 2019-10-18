# Copyright 2019 Capital One Services, LLC
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

from .azure_common import BaseTest, arm_template
from c7n_azure.session import Session
from c7n_azure import utils

from . import tools_tags as tools


class FunctionalActionsTagsTest(BaseTest):

    rg_name = 'test_vm'
    vm_name = 'cctestvm'
    DAYS = 10

    initial_tags = {}

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(FunctionalActionsTagsTest, cls).setUpClass(*args, **kwargs)
        cls.client = Session().client('azure.mgmt.compute.ComputeManagementClient')

        try:
            cls.initial_tags = tools.get_tags(cls.client, cls.rg_name, cls.vm_name)
            tools.set_tags(cls.client, cls.rg_name, cls.vm_name, {})
        except Exception:
            # Can fail without real auth
            pass

    @classmethod
    def tearDownClass(cls, *args, **kwargs):
        super(FunctionalActionsTagsTest, cls).tearDownClass(*args, **kwargs)
        try:
            tools.set_tags(cls.client, cls.rg_name, cls.vm_name, cls.initial_tags)
        except Exception:
            # Can fail without real auth
            pass

    @arm_template('vm.json')
    def test_tag(self):
        self._run_policy([{'type': 'tag', 'tag': 'cctest_tag', 'value': 'ccvalue'}])
        self.assertEqual(self._get_tags().get('cctest_tag'), 'ccvalue')

    @arm_template('vm.json')
    def test_untag(self):
        self._set_tags({'cctest_untag': 'ccvalue'})
        self._run_policy([{'type': 'untag', 'tags': ['cctest_untag']}])
        self.assertEqual(self._get_tags().get('cctest_untag'), None)

    @arm_template('vm.json')
    def test_trim(self):
        self._set_tags({'cctest_trim': 'ccvalue'})
        self._run_policy([{'type': 'tag-trim', 'space': 0}])
        self.assertEqual(self._get_tags().get('cctest_trim'), None)

    @arm_template('vm.json')
    def test_mark_for_op(self):
        self._run_policy([{'type': 'mark-for-op',
                           'tag': 'cctest_mark',
                           'op': 'delete',
                           'msg': '{op}, {action_date}',
                           'days': self.DAYS}])

        expected_date = utils.now() + datetime.timedelta(days=self.DAYS)
        expected = 'delete, ' + expected_date.strftime('%Y/%m/%d')
        self.assertEqual(self._get_tags().get('cctest_mark'), expected)

    @arm_template('vm.json')
    def test_autotag_user_and_date(self):
        self._run_policy([{'type': 'auto-tag-user', 'tag': 'cctest_email', 'days': 1},
                          {'type': 'auto-tag-date', 'tag': 'cctest_date', 'days': 1}])
        self.assertIsNotNone(self._get_tags().get('cctest_email'))
        self.assertIsNotNone(self._get_tags().get('cctest_date'))

    def _get_tags(self):
        return tools.get_tags(self.client, self.rg_name, self.vm_name)

    def _set_tags(self, tags):
        tools.set_tags(self.client, self.rg_name, self.vm_name, tags)

    def _run_policy(self, actions):
        return self.load_policy({
            'name': 'test-tag',
            'resource': 'azure.vm',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'op': 'eq',
                'value_type': 'normalize',
                'value': self.vm_name
            }],
            'actions': actions
        }).run()
