# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from unittest import TestCase

from dateutil import tz
from freezegun import freeze_time

from c7n_azure.filters import AzureOffHour, AzureOnHour


class AzureOffHoursTest(TestCase):

    filter_types = ((AzureOnHour, 'on', 2, 8), (AzureOffHour, 'off', 5, 19))

    def make_filter(self, filter_type, time_type, default_hour, **options):
        data = {
            'type': '{}hour'.format(time_type),
            '{}hour'.format(time_type): default_hour,
            'default_tz': 'America/Toronto',
            'tag': 'schedule',
        }
        data.update(options)
        return filter_type(data).validate()

    def matches_at(self, f, resource, hour, day=7, timezone='America/Toronto'):
        instant = datetime.datetime(2026, 1, day, hour, tzinfo=tz.gettz(timezone))
        with freeze_time(instant):
            return f(resource)

    def test_missing_tag_uses_fallback(self):
        for filter_type, time_type, fallback_hour, default_hour in self.filter_types:
            for opt_out in (False, True):
                for key in ('fallback-schedule', 'fallback_schedule'):
                    for tags in (None, {}, {'maintenance': 'yes'}):
                        with self.subTest(filter=time_type, opt_out=opt_out, key=key, tags=tags):
                            f = self.make_filter(filter_type, time_type, default_hour, **{
                                key: '{}=(W,{})'.format(time_type, fallback_hour),
                                'opt-out': opt_out,
                            })
                            resource = {'InstanceId': 'vm'}
                            if tags is not None:
                                resource['tags'] = tags
                            self.assertTrue(self.matches_at(f, resource, fallback_hour))
                            self.assertFalse(self.matches_at(f, resource, default_hour))
                            self.assertFalse(self.matches_at(f, resource, fallback_hour, day=8))

    def test_resource_tag_overrides_fallback(self):
        for filter_type, time_type, fallback_hour, default_hour in self.filter_types:
            with self.subTest(filter=time_type):
                f = self.make_filter(filter_type, time_type, default_hour, **{
                    'fallback-schedule': '{}=(W,{})'.format(time_type, fallback_hour),
                })
                resource = {
                    'InstanceId': 'vm',
                    'tags': {'ScHeDuLe': '"{}=(W,{})"'.format(
                        time_type.upper(), fallback_hour + 1)},
                }
                self.assertFalse(self.matches_at(f, resource, fallback_hour))
                self.assertTrue(self.matches_at(f, resource, fallback_hour + 1))

    def test_empty_tag_uses_policy_defaults(self):
        for filter_type, time_type, fallback_hour, default_hour in self.filter_types:
            with self.subTest(filter=time_type):
                f = self.make_filter(filter_type, time_type, default_hour, **{
                    'fallback-schedule': '{}=(W,{})'.format(time_type, fallback_hour),
                })
                resource = {'InstanceId': 'vm', 'tags': {'schedule': ''}}
                self.assertFalse(self.matches_at(f, resource, fallback_hour))
                self.assertTrue(self.matches_at(f, resource, default_hour))

    def test_off_tag_overrides_fallback(self):
        for filter_type, time_type, fallback_hour, default_hour in self.filter_types:
            for opt_out in (False, True):
                with self.subTest(filter=time_type, opt_out=opt_out):
                    f = self.make_filter(filter_type, time_type, default_hour, **{
                        'fallback-schedule': '{}=(W,{})'.format(time_type, fallback_hour),
                        'opt-out': opt_out,
                    })
                    resource = {'InstanceId': 'vm', 'tags': {'schedule': 'OFF'}}
                    self.assertFalse(self.matches_at(f, resource, fallback_hour))
                    self.assertEqual(f.opted_out, [resource])

    def test_missing_tag_without_fallback(self):
        for filter_type, time_type, _, default_hour in self.filter_types:
            for opt_out in (False, True):
                with self.subTest(filter=time_type, opt_out=opt_out):
                    f = self.make_filter(filter_type, time_type, default_hour, **{
                        'opt-out': opt_out,
                    })
                    self.assertEqual(
                        self.matches_at(f, {'InstanceId': 'vm'}, default_hour), opt_out)

    def test_fallback_timezone_overrides_policy_timezone(self):
        for filter_type, time_type, fallback_hour, default_hour in self.filter_types:
            with self.subTest(filter=time_type):
                f = self.make_filter(filter_type, time_type, default_hour, **{
                    'fallback-schedule': '"{}=(W,{});TZ=UTC"'.format(
                        time_type.upper(), fallback_hour),
                })
                resource = {'InstanceId': 'vm', 'tags': {}}
                self.assertTrue(self.matches_at(f, resource, fallback_hour, timezone='UTC'))
                self.assertFalse(self.matches_at(f, resource, fallback_hour))
