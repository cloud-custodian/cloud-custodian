# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from unittest.mock import Mock

from dateutil import tz as tzutils

from c7n.testing import mock_datetime_now
from c7n_azure.filters import AzureOffHour, AzureOnHour
from . import tools_tags as tools
from .azure_common import BaseTest


class AzureOffHoursFilterTest(BaseTest):

    def _get_manager(self):
        manager = Mock()
        manager.get_model().id = 'id'
        manager.ctx.log_dir = None
        return manager

    def test_offhour_schema_validate(self):
        self.assertTrue(
            self.load_policy(
                tools.get_policy(filters=[
                    {
                        'type': 'offhour',
                        'default_tz': 'pt',
                        'offhour': 18,
                        'fallback-schedule': 'off=[(M-F,18)];tz=pt',
                    },
                    {
                        'type': 'onhour',
                        'default_tz': 'pt',
                        'onhour': 8,
                        'fallback-schedule': 'on=[(M-F,8)];tz=pt',
                    },
                ]), validate=True))

    def test_offhours_get_tag_value_fallback_when_tag_missing(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
            'fallback-schedule': 'off=[(M-F,18)];tz=pt',
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertEqual(off.get_tag_value(resource), 'off=[(m-f,18)];tz=pt')

    def test_offhours_get_tag_value_fallback_quoted(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
            'fallback-schedule': '"off=[(M-F,18)];tz=pt"',
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertEqual(off.get_tag_value(resource), 'off=[(m-f,18)];tz=pt')

    def test_offhours_get_tag_value_fallback_underscore_alias(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
            'fallback_schedule': 'off=[(M-F,18)];tz=pt',
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertEqual(off.get_tag_value(resource), 'off=[(m-f,18)];tz=pt')

    def test_offhours_get_tag_value_no_fallback_when_tag_missing(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertFalse(off.get_tag_value(resource))

    def test_offhours_get_tag_value_tag_present_overrides_fallback(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
            'fallback-schedule': 'off=[(M-F,18)];tz=pt',
        }, self._get_manager())
        resource = tools.get_resource({'schedule': 'off=[(M-F,20)];tz=pt'})
        self.assertEqual(off.get_tag_value(resource), 'off=[(m-f,20)];tz=pt')

    def test_onhours_get_tag_value_fallback_when_tag_missing(self):
        on = AzureOnHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'onhour': 8,
            'fallback-schedule': 'on=[(M-F,8)];tz=pt',
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertEqual(on.get_tag_value(resource), 'on=[(m-f,8)];tz=pt')

    def test_onhours_get_tag_value_no_fallback_when_tag_missing(self):
        on = AzureOnHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'onhour': 8,
        }, self._get_manager())
        resource = tools.get_resource({})
        self.assertFalse(on.get_tag_value(resource))

    def test_onhours_get_tag_value_tag_present_overrides_fallback(self):
        on = AzureOnHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'onhour': 8,
            'fallback-schedule': 'on=[(M-F,8)];tz=pt',
        }, self._get_manager())
        resource = tools.get_resource({'schedule': 'on=[(M-F,10)];tz=pt'})
        self.assertEqual(on.get_tag_value(resource), 'on=[(m-f,10)];tz=pt')

    def test_offhour_filter_process_with_fallback_schedule(self):
        off = AzureOffHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'offhour': 18,
            'fallback-schedule': 'off=[(M-F,18)];tz=pt',
        }, self._get_manager())

        res_no_tag = tools.get_resource({})
        res_with_tag_diff_hour = tools.get_resource({'schedule': 'off=[(M-F,20)];tz=pt'})
        res_with_tag_diff_hour['id'] = (
            '/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm2'
        )

        t = datetime.datetime.now(tzutils.gettz('pt')).replace(
            year=2018, month=8, day=24, hour=18, minute=30
        )
        with mock_datetime_now(t, datetime):
            matched = off.process([res_no_tag, res_with_tag_diff_hour])
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]['id'], res_no_tag['id'])

    def test_onhour_filter_process_with_fallback_schedule(self):
        on = AzureOnHour({
            'tag': 'schedule',
            'default_tz': 'pt',
            'onhour': 8,
            'fallback-schedule': 'on=[(M-F,8)];tz=pt',
        }, self._get_manager())

        res_no_tag = tools.get_resource({})
        res_with_tag_diff_hour = tools.get_resource({'schedule': 'on=[(M-F,10)];tz=pt'})
        res_with_tag_diff_hour['id'] = (
            '/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm2'
        )

        t = datetime.datetime.now(tzutils.gettz('pt')).replace(
            year=2018, month=8, day=24, hour=8, minute=30
        )
        with mock_datetime_now(t, datetime):
            matched = on.process([res_no_tag, res_with_tag_diff_hour])
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]['id'], res_no_tag['id'])
