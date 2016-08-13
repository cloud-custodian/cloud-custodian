# Copyright 2016 Capital One Services, LLC
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
"""
Offhours support
================

Turn resources off based on a schedule. There are two usage modes that
can be configured, opt-in with resources that wish to participate
specifying a tag value with their configuration for
offhours. Additionally opt-out where the schedule is set to apply to
all resources that match the policy filters, resources can specify a
tag value then to allow opt-out behavior.

Schedules
=========

The default off hours and on hours are specified per the policy configuration
along with the opt-in/opt-out behavior. Resources can specify the timezone
that they wish to have this scheduled utilized with.


Tag Based Configuration
=======================

Note the tag name is configurable per policy configuration, examples below use
default tag name, ie. custodian_downtime.

- custodian_downtime:

An empty tag value implies night and weekend offhours using the default
time zone configured in the policy (tz=est if unspecified).

- custodian_downtime: tz=pt

Note all timezone aliases are referenced to a locality to ensure taking into
account local daylight savings time (if any).

- custodian_downtime: tz=Americas/Los_Angeles

A geography can be specified but must be in the time zone database.

Per http://www.iana.org/time-zones

- custodian_downtime: off

If offhours is configured to run in opt-out mode, this tag can be specified
to disable offhours on a given instance.


Policy examples
===============

Turn ec2 instances on and off

.. code-block:: yaml

   policies:
     - name: offhours-stop
       resource: ec2
       filters:
          - type: offhour
       actions:
         - stop

     - name: offhours-start
       resource: ec2
       filters:
         - type: onhour
       actions:
         - start

Here's doing the same with auto scale groups

.. code-block:: yaml

    policies:
      - name: asg-offhours-stop
        resource: ec2
        filters:
           - type: offhour
        actions:
           - suspend
      - name: asg-onhours-start
        resource: ec2
        filters:
           - type: onhour
        actions:
           - resume


Options
=======

- tag: the tag name to use when configuring
- default_tz: the default timezone to use when interpreting offhours
- offhour: the time to turn instances off, specified in 0-24
- onhour: the time to turn instances on, specified in 0-24
- opt-out: default behavior is opt in, as in ``tag`` must be present,
  with opt-out: true, the tag doesn't need to be present.


.. code-block:: yaml

   policies:
     - name: offhours-stop
       resource: ec2
       filters:
         - type: offhour
           tag: downtime
           onhour: 8
           offhour: 20

"""
from c7n.filters import Filter

import datetime
import logging

from dateutil import zoneinfo

from c7n.utils import type_schema

DEFAULT_TAG = "maid_offhours"

TZ_ALIASES = {
    'pdt': 'America/Los_Angeles',
    'pt': 'America/Los_Angeles',
    'pst': 'America/Los_Angeles',
    'est': 'America/New_York',
    'edt': 'America/New_York',
    'et': 'America/New_York',
    'cst': 'America/Chicago',
    'cdt': 'America/Chicago',
    'ct': 'America/Chicago',
    'mt': 'America/Denver',
    'gmt': 'Europe/London',
    'gt': 'Europe/London'
}

TIME_ALIASES = {
    'w': 'week',
    'd': 'day',
    'm': 'month',
    'y': 'year'
}

DEFAULT_OFFHOUR = 19
DEFAULT_ONHOUR = 7
DEFAULT_TZ = 'et'

VALID_DAYS = ['m', 't', 'w', 'h', 'f', 's', 'u']
VALID_HOURS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
               19, 20, 21, 22, 23)

log = logging.getLogger('custodian.offhours')


def resource_id(i):
    if 'InstanceId' in i:
        return "instance:%s" % i['InstanceId']
    if 'AutoScalingGroupName' in i:
        return "asg:%s" % i['AutoScalingGroupName']


class Time(Filter):

    schema = {
        'type': 'object',
        'properties': {
            'tag': {'type': 'string'},
            'default_tz': {'type': 'string'},
            'skew': {'type': 'integer'},
            'weekends': {'type': 'boolean'},
            'opt-out': {'type': 'boolean'},
            }
        }

    # Allow up to this many hours after sentinel time
    # to continue to match
    skew = 0
    time_type = None

    def __init__(self, data, manager=None):
        super(Time, self).__init__(data, manager)
        self.skew = self.data.get('skew', self.skew)
        self.weekends = self.data.get('weekends', False)
        self.opt_out = self.data.get('opt-out', False)

    def __call__(self, i):
        parts, tag_map = self.get_tag_parts(i)
        if parts is False:
            if self.opt_out:
                parts = []
            else:
                return False
        if 'off' in parts:
            log.debug('offhours disabled on %s' % resource_id(i))
            return False
        return self.process_current_time(i, parts)

    def process_current_time(self, i, parts):
        try:
            parsed = ScheduleParser().parse(parts[0])
        except Exception as e:
            log.warning("Parsing Error: %s. Using default values" % e)
            parsed = ScheduleParser().parse("")

        tz_part = ['tz=%s' % parsed.get('tz')]
        tz = self.get_local_tz(tz_part)
        if not tz:
            return False

        now = datetime.datetime.now(tz).replace(
            minute=0, second=0, microsecond=0)

        #override get_sentinel_time with get_custom_time if custom downtime
        #detected
        if self.is_custom(parsed):
            return self.get_custom_time(i, now, parsed)

        if not self.weekends and now.weekday() in (5, 6):
            log.debug("skipping weekends")
            return False

        sentinel = self.get_sentinel_time(tz)

        log.debug(
            "resource: %s comparing sentinel: %s to current: %s" % (
                resource_id(i), sentinel, now))

        if sentinel == now:
            return True
        if not self.skew:
            return False
        hour = sentinel.hour
        for i in range(1, self.skew + 1):
            sentinel = sentinel.replace(hour=hour + i)
            if sentinel == now:
                return True
        return False

    def get_tag_parts(self, i):
        # Look for downtime tag, Normalize tag key and tag value
        tag_key = self.data.get('tag', DEFAULT_TAG).lower()
        tag_map = {t['Key'].lower(): t['Value'] for t in i.get('Tags', [])}
        if tag_key not in tag_map:
            return False, tag_map
        value = tag_map[tag_key].lower()
        # Sigh.. some folks seem to be interpreting the docs quote marks as
        # literal for values.
        value = value.strip("'").strip('"')
        parts = filter(None, value.split())
        log.debug('resource: %s specifies downtime with value: %s' % (
            resource_id(i), value))
        return parts, tag_map

    def get_sentinel_time(self, tz):
        t = datetime.datetime.now(tz)
        return t.replace(
            hour=self.data.get('hour', 0),
            minute=self.data.get('minute', 0),
            second=0,
            microsecond=0)

    def get_local_tz(self, parts):
        tz_spec = None
        for p in parts:
            if p.startswith('tz='):
                tz_spec = p
                break
        if tz_spec is None:
            tz_spec = (
                self.data.get('default_tz') or
                self.data.get('default-tz', DEFAULT_TZ))
        else:
            _, tz_spec = tz_spec.split('=')

        if tz_spec in TZ_ALIASES:
            tz_spec = TZ_ALIASES[tz_spec]
        tz = zoneinfo.gettz(tz_spec)
        if tz is None:
            self.log.warning(
                "filter:offhours unknown tz %s for %s" % (
                    tz_spec, parts))

            return None
        return tz


    def is_custom(self, parts):
        return "tz" in parts and "on" in parts and "off" in parts


    def get_custom_time(self, i, now, parts):
        if self.time_type is None:
            return False

        time = parts.get(self.time_type)
        tz = parts.get("tz")

        for item in time:
            days = item.get("days")
            hour = item.get("hour")
            for d in days:
                log.debug("resource: %s checking custom hours, day=%s "
                     "hour=%s, and tz=%s" % (resource_id(i), d, hour, tz))
                if now.weekday() == VALID_DAYS.index(d): #if today
                    if now.hour == hour:
                        log.debug("resource: %s matches custom hours with "
                                  "value now: %s" % (resource_id(i), now))
                        return True
        log.debug("No custom hours match found for resource: %s" % resource_id(i))
        return False


class OffHour(Time):

    schema = type_schema(
        'offhour', rinherit=Time.schema, required=['offhour', 'default_tz'],
        offhour={'type': 'integer', 'minimum': 0, 'maximum': 24})
    time_type = "off"

    def get_sentinel_time(self, tz):
        t = super(OffHour, self).get_sentinel_time(tz)
        return t.replace(hour=self.data.get('offhour', DEFAULT_OFFHOUR))


class OnHour(Time):

    schema = type_schema(
        'onhour', rinherit=Time.schema, required=['onhour', 'default_tz'],
        onhour={'type': 'integer', 'minimum': 0, 'maximum': 24})
    time_type = "on"

    def get_sentinel_time(self, tz):
        t = super(OnHour, self).get_sentinel_time(tz)
        return t.replace(hour=self.data.get('onhour', DEFAULT_ONHOUR))



class ScheduleParser:
    """
    The ScheduleParser class parses instances/asgs to define a custom off hours
    schedule via the offhours tag.

    At the minimum the ``on`` and ``off`` tags are required. Each of these must
    be seperated by a ``;`` in the format described below.

    **Schedule format**::

        # up mon-fri from 7am-7pm; eastern time
        off=(M-F,19);on=(M-F,7)
        # up mon-fri from 6am-9pm; up sun from 10am-6pm; pacific time
        off=[(M-F,21),(U,18)];on=[(M-F,6),(U,10)];tz=pt

    **Possible values**:

        +------------+----------------------+
        | field      | values               |
        +============+======================+
        | days       | M, T, W, H, F, S, U  |
        +------------+----------------------+
        | hours      | 1, 2, 3, ..., 22, 23 |
        +------------+----------------------+

        Days can be specified in a range (ex. M-F).

    If the timezone is not supplied, it is assumed ET (eastern time), but this
    default can be configurable.

    **Parser output**:

    The schedule parser will return a ``dict`` or ``None`` (if the schedule is
    invalid)::

        # off=[(M-F,21),(U,18)];on=[(M-F,6),(U,10)];tz=pt
        {
          off: [
            { days: "M-F", hour: 21 },
            { days: "U", hour: 18 }
          ],
          on: [
            { days: "M-F", hour: 6 },
            { days: "U", hour: 10 }
          ],
          tz: "pt"
        }
    """

    cache = {}

    def parse(self, tag_value):
        # check the cache
        if tag_value in self.cache:
            return self.cache[tag_value]
        schedule = {}
        # parse schedule components
        pieces = tag_value.split(';')
        for piece in pieces:
            kv = piece.split('=')
            # components must by key-value
            if not len(kv) == 2:
                continue
            key = kv[0].strip()
            value = kv[1].strip()
            if key == 'on' or key == 'off':
                # parse custom on/off hours
                value = self.parse_custom_hours(value)
            schedule[key] = value
        # add default timezone, if none supplied or blank
        if schedule.get('tz') is None  or not schedule.get('tz'):
            schedule['tz'] = DEFAULT_TZ
        # validate
        if not self.is_valid(schedule):
            schedule = None
        # cache
        self.cache[tag_value] = schedule
        return schedule

    def parse_custom_hours(self, hours):
        parsed = []
        hours = hours.translate(None, '[]').split(',(')
        for hour in hours:
            hour = hour.translate(None, '()').split(',')
            # custom hours must have two parts: (<days>, <hour>)
            if not len(hour) == 2:
                #force an all or nothing senario in terms of bad values
                return []
            try:
                hour[1] = int(hour[1])
                if not self.is_valid_hour_range(hour[1]):
                    raise ValueError("The specified hour is invalid")
                parsed.append({
                    'days': self.expand_day_range(hour[0]),
                    'hour': hour[1]
                    })
            except ValueError:
                #force an all or nothing senario in terms of bad values
                raise
        return parsed

    def expand_day_range(self, days):
        if len(days) == 1:
            if not self.is_valid_day(days):
                raise ValueError("The specified day is invalid")
            return [days]

        days = days.split('-')
        if not len(days) == 2:
            return []

        if not self.is_valid_day(days[0]) or not self.is_valid_day(days[1]):
            raise ValueError("The specificed day is invalid")
        # return a slice of valid days
        return VALID_DAYS[VALID_DAYS.index(days[0]):VALID_DAYS.index(days[1])+1]

    def is_valid(self, schedule):
        # off and on are both required if either is present
        if 'off' in schedule and 'on' not in schedule:
            raise ValueError("On tag is missing or malformed")
        elif 'on' in schedule and 'off' not in schedule:
            raise ValueError("Off tag is missing or malformed")
        # validate custom on/off hours
        if 'off' in schedule and 'on' in schedule:
            if not self.is_valid_hours(schedule['off']):
                raise ValueError("The specificed Off hour value is invalid")
            if not self.is_valid_hours(schedule['on']):
                raise ValueError("The specificed On hour value is invalid")
        return True

    def is_valid_hours(self, hours):
        if len(hours) <= 0:
            return False
        for hour in hours:
            if not self.is_valid_hour(hour):
                return False
        return True

    def is_valid_hour(self, hour):
        if len(hour['days']) <= 0:
            return False
        return True

    def is_valid_hour_range(self, hour):
        if hour in VALID_HOURS:
            return True
        return False

    def is_valid_day(self, day):
        if day in VALID_DAYS:
            return True
        return False
