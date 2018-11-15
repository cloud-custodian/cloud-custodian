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

import datetime
from dateutil import zoneinfo

from azure_common import BaseTest, arm_template

from c7n.testing import mock_datetime_now


class AppServicePlanTest(BaseTest):
    def setUp(self):
        super(AppServicePlanTest, self).setUp()

    def test_app_service_plan_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-appserviceplan',
                'resource': 'azure.appserviceplan',
                'filters': [
                    {'type': 'offhour',
                     'default_tz': "pt",
                     'offhour': 18,
                     'tag': 'schedule'},
                    {'type': 'onhour',
                     'default_tz': "pt",
                     'onhour': 18,
                     'tag': 'schedule'}],
                'actions': [
                    {'type': 'resize-plan',
                     'size': 'F1'}],
            }, validate=True)
            self.assertTrue(p)

    @arm_template('appserviceplan.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-appserviceplan',
            'resource': 'azure.appserviceplan',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctest-appserviceplan'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('appserviceplan.json')
    def test_resize_plan(self):
        p = self.load_policy({
            'name': 'test-azure-appserviceplan',
            'resource': 'azure.appserviceplan',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctest-appserviceplan'}],
            'actions': [
                {'type': 'resize-plan',
                 'size': 'F1'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('appserviceplan.json')
    def test_on_off_hours(self):
        t = datetime.datetime.now(zoneinfo.gettz("pt"))
        t = t.replace(year=2018, month=8, day=24, hour=18, minute=30)

        with mock_datetime_now(t, datetime):
            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'offhour',
                     'default_tz': "pt",
                     'offhour': 18,
                     'tag': 'schedule'}
                ],
            })

            resources = p.run()
            self.assertEqual(len(resources), 1)

        t = t.replace(year=2018, month=8, day=24, hour=8, minute=30)

        with mock_datetime_now(t, datetime):
            p = self.load_policy({
                'name': 'test-azure-vm',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'onhour',
                     'default_tz': "pt",
                     'onhour': 8,
                     'tag': 'schedule'}
                ],
            })

            resources = p.run()
            self.assertEqual(len(resources), 1)
