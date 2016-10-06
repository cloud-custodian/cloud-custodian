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
Resource Scheduling Offhours
============================

Custodian provides for time based filters, that allow for taking periodic
action on a resource, with resource schedule customization based on tag values.
A common use is offhours scheduling for asgs, and instances.

Features
========

- Flexible offhours scheduling with opt-in, opt-out selection, and timezone
  support.
- Resume during offhours support.
- Can be combined with other filters to get a particular set (
  resources with tag, vpc, etc).
- Can be combined with arbitrary actions

Policy Configuration
====================

We provide an `onhour` and `offhour` time filter, each should be used in a
different policy, they support the same configuration options

 - :weekends: default true, whether to leave resources off for the weekend
 - :weekend-only: default false, whether to turn the resource off only on the
   weekend
 - :default_tz: which tz to utilize when evaluating time
 - :tag: default maid_offhours, which resource tag key to look for the
   resource's schedule.
 - :opt-out: applies the default schedule to resource which do not specify
   any value. a value of `off` to disable/exclude the resource.

The default off hours and on hours are specified per the policy configuration
along with the opt-in/opt-out behavior. Resources can specify the timezone
that they wish to have this scheduled utilized with::


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
           - offhour
        actions:
           - suspend
      - name: asg-onhours-start
        resource: ec2
        filters:
           - onhour
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

# note we have to module import for our testing mocks
import datetime
import logging
from os.path import join

from dateutil import zoneinfo

from c7n.filters import Filter, FilterValidationError
from c7n.utils import type_schema, dumps

log = logging.getLogger('custodian.offhours')


class Time(Filter):

    schema = {
        'type': 'object',
        'properties': {
            'tag': {'type': 'string'},
            'default_tz': {'type': 'string'},
            'weekends': {'type': 'boolean'},
            'weekends-only': {'type': 'boolean'},
            'opt-out': {'type': 'boolean'},
            'debug': {'type': 'boolean'},
            }
        }

    time_type = None

    # Defaults and constants
    DEFAULT_TAG = "maid_offhours"
    DEFAULT_TZ = 'et'

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
        'gt': 'Europe/London'}

    def __init__(self, data, manager=None):
        super(Time, self).__init__(data, manager)
        self.default_tz = self.data.get('default_tz', self.DEFAULT_TZ)
        self.weekends = self.data.get('weekends', True)
        self.weekends_only = self.data.get('weekends-only', False)
        self.opt_out = self.data.get('opt-out', False)
        self.tag_key = self.data.get('tag', self.DEFAULT_TAG).lower()
        self.default_schedule = self.get_default_schedule()
        self.parser = ScheduleParser(self.default_schedule)

        self.id_key = None

        self.opted_out = []
        self.parse_errors = []
        self.enabled_count = 0

    def validate(self):
        if self.get_tz(self.default_tz) is None:
            raise FilterValidationError(
                "Invalid timezone specified %s" % self.default_tz)
        hour = self.data.get("%shour" % self.time_type, self.DEFAULT_HR)
        if hour not in self.parser.VALID_HOURS:
            raise FilterValidationError("Invalid hour specified %s" % hour)
        return self

    def process(self, resources, event=None):
        resources = super(Time, self).process(resources)
        if self.parse_errors and self.manager and self.manager.log_dir:
            self.log.warning("parse errors %d", len(self.parse_errors))
            with open(join(
                    self.manager.log_dir, 'parse_errors.json'), 'w') as fh:
                dumps(self.parse_errors, fh=fh)
            self.parse_errors = []
        if self.opted_out and self.manager and self.manager.log_dir:
            self.log.debug("disabled count %d", len(self.opted_out))
            with open(join(
                    self.manager.log_dir, 'opted_out.json'), 'w') as fh:
                dumps(self.opted_out, fh=fh)
            self.opted_out = []
        return resources

    def __call__(self, i):
        value = self.get_tag_value(i)
        # Sigh delayed init, due to circle dep, process/init would be better but
        # unit testing is calling this direct.
        if self.id_key is None:
            self.id_key = (
                self.manager is None and 'InstanceId'
                or self.manager.get_model().id)

        # The resource tag is not present, if we're not running in an opt-out
        # mode, we're done.
        if value is False:
            if not self.opt_out:
                return False
            value = "" # take the defaults

        # Resource opt out, track and record
        if 'off' == value:
            self.opted_out.append(i)
            return False
        else:
            self.enabled_count += 1

        try:
            return self.process_resource_schedule(i, value)
        except:
            log.exception(
                "%s failed to process resource:%s value:%s",
                self.__class__.__name__, i[self.id_key], value)
            return False

    def process_resource_schedule(self, i, value):
        """Does the resource tag schedule and policy match the current time."""
        rid = i[self.id_key]
        if self.parser.has_resource_schedule(value):
            schedule = self.parser.parse(value)
        else:
            schedule = self.default_schedule

        if schedule is None:
            log.warning(
                "Invalid schedule on resource:%s value:%s", rid, value)
            self.parse_errors.append((rid, value))
            return False

        tz = self.get_tz(schedule['tz'])
        if not tz:
            log.warning(
                "Could not resolve tz on resource:%s value:%s", rid, value)
            self.parse_errors.append((rid, value))
            return False

        now = datetime.datetime.now(tz).replace(
            minute=0, second=0, microsecond=0)
        return self.match(now, schedule)

    def match(self, now, schedule):
        time = schedule.get(self.time_type, ())
        for item in time:
            days, hour = item.get("days"), item.get('hour')
            if now.weekday() in days and now.hour == hour:
                return True
        return False

    def get_tag_value(self, i):
        """Get the resource's tag value specifying its schedule."""
        # Look for the tag, Normalize tag key and tag value
        found = False
        for t in i.get('Tags', ()):
            if t['Key'].lower() == self.tag_key:
                found = t['Value']
        if found is False:
            return False
        # utf8, or do translate tables via unicode ord mapping
        value = found.lower().encode('utf8')
        # Some folks seem to be interpreting the docs quote marks as
        # literal for values.
        value = value.strip("'").strip('"').translate(None, ' ')
        return value

    @classmethod
    def get_tz(cls, tz):
        return zoneinfo.gettz(cls.TZ_ALIASES.get(tz, tz))

    def get_default_schedule(self):
        raise NotImplementedError("use subclass")


class OffHour(Time):

    schema = type_schema(
        'offhour', rinherit=Time.schema, required=['offhour', 'default_tz'],
        offhour={'type': 'integer', 'minimum': 0, 'maximum': 24})
    time_type = "off"

    DEFAULT_HR = 19

    def get_default_schedule(self):
        default = {'tz': self.default_tz, self.time_type: [
            {'hour': self.data.get(
                "%shour" % self.time_type, self.DEFAULT_HR)}]}
        if self.weekends_only:
            default[self.time_type][0]['days'] = [4]
        elif self.weekends:
            default[self.time_type][0]['days'] = range(5)
        else:
            default[self.time_type][0]['days'] = range(7)
        return default


class OnHour(Time):

    schema = type_schema(
        'onhour', rinherit=Time.schema, required=['onhour', 'default_tz'],
        onhour={'type': 'integer', 'minimum': 0, 'maximum': 24})
    time_type = "on"

    DEFAULT_HR = 7

    def get_default_schedule(self):
        default = {'tz': self.default_tz, self.time_type: [
            {'hour': self.data.get(
                "%shour" % self.time_type, self.DEFAULT_HR)}]}
        if self.weekends_only:
            # turn on monday
            default[self.time_type][0]['days'] = [0]
        elif self.weekends:
            default[self.time_type][0]['days'] = range(5)
        else:
            default[self.time_type][0]['days'] = range(7)
        return default


class ScheduleParser(object):
    """Parses tag values for custom on/off hours schedules.

    At the minimum the ``on`` and ``off`` values are required. Each of
    these must be seperated by a ``;`` in the format described below.

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
        | hours      | 0, 1, 2, ..., 22, 23 |
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

    DAY_MAP = {'m': 0, 't': 1, 'w': 2, 'h': 3, 'f': 4, 's': 5, 'u': 6}
    VALID_HOURS = tuple(range(24))

    def __init__(self, default_schedule):
        self.default_schedule = default_schedule
        self.cache = {}

    def parse(self, tag_value):
        # check the cache
        if tag_value in self.cache:
            return self.cache[tag_value]

        schedule = {}

        # parse schedule components
        pieces = tag_value.split(';')
        for piece in pieces:
            kv = piece.split('=')
            # components must by key=value
            if not len(kv) == 2:
                return None
            key, value = kv
            if key not in ('on', 'off', 'tz'):
                return None
            if key != 'tz':
                value = self.parse_resource_schedule(value)
            if value is None:
                return None
            schedule[key] = value

        # add default timezone, if none supplied or blank
        if not schedule.get('tz'):
            schedule['tz'] = self.default_schedule['tz']

        # cache
        self.cache[tag_value] = schedule
        return schedule

    @staticmethod
    def has_resource_schedule(tag_value):
        if 'off=' in tag_value and 'on=' in tag_value:
            return True
        return False

    def parse_resource_schedule(self, lexeme):
        parsed = []
        exprs = lexeme.translate(None, '[]').split(',(')
        for e in exprs:
            tokens = e.translate(None, '()').split(',')
            # custom hours must have two parts: (<days>, <hour>)
            if not len(tokens) == 2:
                return None
            if not tokens[1].isdigit():
                return None
            hour = int(tokens[1])
            if hour not in self.VALID_HOURS:
                return None
            days = self.expand_day_range(tokens[0])
            if not days:
                return None
            parsed.append({'days': days, 'hour': hour})
        return parsed

    def expand_day_range(self, days):
        # single day specified
        if days in self.DAY_MAP:
            return [self.DAY_MAP[days]]
        day_range = [d for d in map(self.DAY_MAP.get, days.split('-'))
                     if d is not None]
        if not len(day_range) == 2:
            return None
        # support wrap around days aka friday-monday = 4,5,6,0
        if day_range[0] > day_range[1]:
            return range(day_range[0], 7) + range(day_range[1]+1)
        return range(min(day_range), max(day_range) + 1)
