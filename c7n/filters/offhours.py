# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Resource Scheduling Offhours
============================

Custodian provides for time based filters, that allow for taking periodic
action on a resource, with resource schedule customization based on tag values.
A common use is offhours scheduling for asgs and instances.

Features
========

- Flexible offhours scheduling with opt-in, opt-out selection, and timezone
  support.
- Resume during offhours support.
- Can be combined with other filters to get a particular set (
  resources with tag, vpc, etc).
- Can be combined with arbitrary actions
- Can omit a set of dates such as public holidays.

Policy Configuration
====================

We provide an `onhour` and `offhour` time filter, each should be used in a
different policy, they support the same configuration options:

 - **weekends**: default true, whether to leave resources off for the weekend
 - **weekends-only**: default false, whether to turn the resource off only on
   the weekend
 - **default_tz**: which timezone to utilize when evaluating time **(REQUIRED)**
 - **fallback-schedule**: If a resource doesn't support tagging or doesn't provide
   a tag you can supply a default schedule that will be used. When the tag is provided
   this will be ignored. See :ref:`ScheduleParser Time Specifications <scheduleparser-time-spec>`.
 - **tag**: which resource tag name to use for per-resource configuration
   (schedule and timezone overrides and opt-in/opt-out); default is
   ``maid_offhours``.
 - **opt-out**: Determines the behavior for resources which do not have a tag
   matching the one specified for **tag**. Values can be either ``false`` (the
   default) where the policy operates on an opt-in basis and resources must have
   the tag in order to be acted on by the policy, or ``true`` where the policy
   operates on an opt-out basis, and resources without the tag are acted on by
   the policy.
 - **onhour**: the default time to start/run resources, specified as 0-23
 - **offhour**: the default time to stop/suspend resources, specified as 0-23
 - **skip-days**: a list of dates to skip. Dates must use format YYYY-MM-DD
 - **skip-days-from**: a list of dates to skip stored at a url. **expr**,
   **format**, and **url** must be passed as parameters. Same syntax as
   ``value_from``. Can not specify both **skip-days-from** and **skip-days**.

This example policy overrides most of the defaults for an offhour policy:

.. code-block:: yaml

   policies:
     - name: offhours-stop
       resource: ec2
       filters:
         - type: offhour
           weekends: false
           default_tz: pt
           tag: downtime
           opt-out: true
           onhour: 8
           offhour: 20


Tag Based Configuration
=======================

Resources can use a special tag to override the default configuration on a
per-resource basis. Note that the name of the tag is configurable via the
``tag`` option in the policy; the examples below use the default tag name,
``maid_offhours``.

The value of the tag must be one of the following:

- **(empty)** or **on** - An empty tag value or a value of "on" implies night
  and weekend offhours using the default time zone configured in the policy
  (tz=est if unspecified) and the default onhour and offhour values configured
  in the policy.
- **off** - If offhours is configured to run in opt-out mode, this tag can be
  specified to disable offhours on a given instance. If offhours is configured
  to run in opt-in mode, this tag will have no effect (the resource will still
  be opted out).
- a semicolon-separated string composed of one or more of the following
  components, which override the defaults specified in the policy:

  * ``tz=<timezone>`` to evaluate with a resource-specific timezone, where
    ``<timezone>`` is either one of the supported timezone aliases defined in
    :py:attr:`c7n.filters.offhours.Time.TZ_ALIASES` (such as ``pt``) or the name
    of a geographic timezone identifier in
    [IANA's tzinfo database](https://www.iana.org/time-zones), such as
    ``Americas/Los_Angeles``. *(Note all timezone aliases are
    referenced to a locality to ensure taking into account local daylight
    savings time, if applicable.)*
  * ``off=(time spec)`` and/or ``on=(time spec)`` matching time specifications
    supported by :py:class:`c7n.filters.offhours.ScheduleParser` as described
    in the next section. Additionally, it's possible to specify ``off=disabled``
    and/or ``on=disabled`` to completly disable offhours stopping (respectively
    starting) - this way you can have a policy to stop ressources, without starting
    them (or vice-verse).


.. _scheduleparser-time-spec:

ScheduleParser Time Specifications
----------------------------------

Each time specification follows the format ``(days,hours)``. Multiple time
specifications can be combined in square-bracketed lists, i.e.
``[(days,hours),(days,hours),(days,hours)]``.

**Examples**::

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
        resource: asg
        filters:
           - offhour
        actions:
           - suspend
      - name: asg-onhours-start
        resource: asg
        filters:
           - onhour
        actions:
           - resume

Additional policy examples and resource-type-specific information can be seen in
the :ref:`EC2 Offhours <ec2offhours>` and :ref:`ASG Offhours <asgoffhours>`
use cases.

Resume During Offhours
======================

These policies are evaluated hourly; during each run (once an hour),
cloud-custodian will act on **only** the resources tagged for that **exact**
hour. In other words, if a resource has an offhours policy of
stopping/suspending at 23:00 Eastern daily and starting/resuming at 06:00
Eastern daily, and you run cloud-custodian once an hour via Lambda, that
resource will only be stopped once a day sometime between 23:00 and 23:59, and
will only be started once a day sometime between 06:00 and 06:59. If the current
hour does not *exactly* match the hour specified in the policy, nothing will be
done at all.

As a result of this, if custodian stops an instance or suspends an ASG and you
need to start/resume it, you can safely do so manually and custodian won't touch
it again until the next day.

ElasticBeanstalk, EFS and Other Services with Tag Value Restrictions
====================================================================

A number of AWS services have restrictions on the characters that can be used
in tag values, such as `ElasticBeanstalk <http://docs.aws.amazon.com/elasticbean
stalk/latest/dg/using-features.tagging.html>`_ and `EFS <http://docs.aws.amazon.
com/efs/latest/ug/API_Tag.html>`_. In particular, these services do not allow
parenthesis, square brackets, commas, or semicolons, or empty tag values. This
proves to be problematic with the tag-based schedule configuration described
above. The best current workaround is to define a separate policy with a unique
``tag`` name for each unique schedule that you want to use, and then tag
resources with that tag name and a value of ``on``. Note that this can only be
used in opt-in mode, not opt-out.

Another option is to escape the tag value with the following mapping, generated
with the char's unicode number `"u" + hex(ord(the_char))[2:]`.
This works for GCP resources as well.

- ( and ) as u28 and u29
- [ and ] as u5b and u5d
- , as u2c
- ; as u3b
- = as u3d
- / as u2f
- - as u2d

**Examples**::

    # off=(M-F,18);tz=Australia/Sydney
    offu3du28M-Fu2c18u29u3btzu3dAustraliau2fSydney
    # off=[(M-F,18),(S,13)]
    off=u5bu28M-Fu2c18u29u2cu28Su2c13u29u5d

Public Holidays
===============

In order to properly implement support for public holidays, make sure to include
either **skip-days** or **skip-days-from** with your policy. This list
should contain all of the public holidays you wish to address and must use
YYYY-MM-DD syntax for its dates. If the date the policy is being run on matches
any one of those dates, the policy will not return any resources. These dates
include year as many holidays vary from year to year so year is required to prevent
errors. A sample policy that would not start stopped instances on a public holiday
might look like:

.. code-block:: yaml

    policies:
        - name: onhour-morning-start-skip-holidays
          resource: ec2
          filters:
            - type: onhour
              tag: custodian_downtime
              default_tz: et
              onhour: 6
              skip-days: ['2017-12-25']
          actions:
            - start

"""
# note we have to module import for our testing mocks
import datetime
import logging
from os.path import join

from dateutil import zoneinfo, tz as tzutil

from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter
from c7n.utils import type_schema, dumps
from c7n.resolver import ValuesFrom

log = logging.getLogger('custodian.offhours')


def brackets_removed(u):
    return u.translate({ord('['): None, ord(']'): None})


def parens_removed(u):
    return u.translate({ord('('): None, ord(')'): None})


class Time(Filter):
    """
    Schedule offhours for resources see :ref:`offhours <offhours>`
    for features and configuration.
    """
    schema = {
        'type': 'object',
        'properties': {
            'tag': {'type': 'string'},
            'default_tz': {'type': 'string'},
            'fallback-schedule': {'type': 'string'},
            'fallback_schedule': {'type': 'string'},
            'weekends': {'type': 'boolean'},
            'weekends-only': {'type': 'boolean'},
            'opt-out': {'type': 'boolean'},
            'skip-days': {'type': 'array', 'items':
                {'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{2}-[0-9]{2}'}},
            'skip-days-from': ValuesFrom.schema,
        }
    }
    schema_alias = True
    time_type = None

    # Defaults and constants
    DEFAULT_TAG = "maid_offhours"
    DEFAULT_TZ = 'et'

    TZ_ALIASES = {
        'pdt': 'America/Los_Angeles',
        'pt': 'America/Los_Angeles',
        'pst': 'America/Los_Angeles',
        'ast': 'America/Phoenix',
        'at': 'America/Phoenix',
        'est': 'America/New_York',
        'edt': 'America/New_York',
        'et': 'America/New_York',
        'cst': 'America/Chicago',
        'cdt': 'America/Chicago',
        'ct': 'America/Chicago',
        'mst': 'America/Denver',
        'mdt': 'America/Denver',
        'mt': 'America/Denver',
        'gmt': 'Etc/GMT',
        'gt': 'Etc/GMT',
        'bst': 'Europe/London',
        'ist': 'Europe/Dublin',
        'cet': 'Europe/Berlin',
        # Technically IST (Indian Standard Time), but that's the same as Ireland
        'it': 'Asia/Kolkata',
        'jst': 'Asia/Tokyo',
        'kst': 'Asia/Seoul',
        'sgt': 'Asia/Singapore',
        'aet': 'Australia/Sydney',
        'brt': 'America/Sao_Paulo',
        'nzst': 'Pacific/Auckland',
        'utc': 'Etc/UTC',
    }
    TAG_RESTRICTIONS = ["(", ")", "[", "]", ",", ";", "=", "/", "-"]
    # mapping to ['u28', 'u29', 'u5b', 'u5d', 'u2c', 'u3b', 'u3d', 'u2f', "u2d"]
    TAG_RESTRICTIONS_ESCAPE = ["u" + hex(ord(c))[2:] for c in TAG_RESTRICTIONS]

    z_names = list(zoneinfo.get_zonefile_instance().zones)
    non_title_case_zones = (
        lambda aliases=TZ_ALIASES.keys(), z_names=z_names:
        {z.lower(): z for z in z_names
            if z.title() != z and z.lower() not in aliases})()
    TZ_ALIASES.update(non_title_case_zones)

    def __init__(self, data, manager=None):
        super(Time, self).__init__(data, manager)
        self.default_tz = self.data.get('default_tz', self.DEFAULT_TZ)
        self.weekends = self.data.get('weekends', True)
        self.weekends_only = self.data.get('weekends-only', False)
        self.opt_out = self.data.get('opt-out', False)
        self.tag_key = self.data.get('tag', self.DEFAULT_TAG).lower()
        # we originally had fallback_schedule, but the code was looking for
        # fallback-schedule, we want to deprecate the underscore form.
        self.fallback_schedule = (
            self.data.get('fallback-schedule') or
            self.data.get('fallback_schedule')
        )
        self.default_schedule = self.get_default_schedule()
        self.parser = ScheduleParser(self.default_schedule)

        self.id_key = None

        self.opted_out = []
        self.parse_errors = []
        self.enabled_count = 0

    def validate(self):
        if self.get_tz(self.default_tz) is None:
            raise PolicyValidationError(
                "Invalid timezone specified %s" % (
                    self.default_tz))
        hour = self.data.get("%shour" % self.time_type, self.DEFAULT_HR)
        if hour not in self.parser.VALID_HOURS:
            raise PolicyValidationError(
                "Invalid hour specified %s" % (hour,))
        if 'skip-days' in self.data and 'skip-days-from' in self.data:
            raise PolicyValidationError(
                "Cannot specify two sets of skip days %s" % (
                    self.data,))
        return self

    def process(self, resources, event=None):
        resources = super(Time, self).process(resources)
        if self.parse_errors and self.manager and self.manager.ctx.log_dir:
            self.log.warning("parse errors %d", len(self.parse_errors))
            with open(join(
                    self.manager.ctx.log_dir, 'parse_errors.json'), 'w') as fh:
                dumps(self.parse_errors, fh=fh)
            self.parse_errors = []
        if self.opted_out and self.manager and self.manager.ctx.log_dir:
            self.log.debug("disabled count %d", len(self.opted_out))
            with open(join(
                    self.manager.ctx.log_dir, 'opted_out.json'), 'w') as fh:
                dumps(self.opted_out, fh=fh)
            self.opted_out = []
        return resources

    def __call__(self, i):
        value = self.get_tag_value(i)
        # Sigh delayed init, due to circle dep, process/init would be better
        # but unit testing is calling this direct.
        if self.id_key is None:
            self.id_key = (
                self.manager is None and 'InstanceId' or self.manager.get_model().id)

        # The resource tag is not present, if we're not running in an opt-out
        # mode, we're done.
        if value is False:
            if not self.opt_out:
                return False
            value = ""  # take the defaults

        # Resource opt out, track and record
        if 'off' == value:
            self.opted_out.append(i)
            return False
        else:
            self.enabled_count += 1

        try:
            return self.process_resource_schedule(i, value, self.time_type)
        except Exception:
            log.exception(
                "%s failed to process resource:%s value:%s",
                self.__class__.__name__, i[self.id_key], value)
            return False

    def process_resource_schedule(self, i, value, time_type):
        """Does the resource tag schedule and policy match the current time."""
        rid = i[self.id_key]
        # this is to normalize trailing semicolons which when done allows
        # dateutil.parser.parse to process: value='off=(m-f,1);' properly.
        # before this normalization, some cases would silently fail.
        value = ';'.join(filter(None, value.split(';')))
        if self.parser.has_resource_schedule(value, time_type):
            schedule = self.parser.parse(value)
        elif self.parser.keys_are_valid(value):
            # respect timezone from tag
            raw_data = self.parser.raw_data(value)
            if 'tz' in raw_data:
                schedule = dict(self.default_schedule)
                schedule['tz'] = raw_data['tz']
            else:
                schedule = self.default_schedule
        else:
            schedule = None
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
        now_str = now.strftime("%Y-%m-%d")
        if 'skip-days-from' in self.data:
            values = ValuesFrom(self.data['skip-days-from'], self.manager)
            self.skip_days = values.get_values()
        else:
            self.skip_days = self.data.get('skip-days', [])
        if now_str in self.skip_days:
            return False
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
        found = self.fallback_schedule
        for t in i.get('Tags', ()):
            if t['Key'].lower() == self.tag_key:
                found = t['Value']
                break
        # NOTE for GCP resources, eg sql-instance
        if found == self.fallback_schedule and 'labels' in i:
            found = i.get('labels', {}).get(self.tag_key) or found
        if found in (False, None):
            return False
        # enforce utf8, or do translate tables via unicode ord mapping
        value = found.lower().encode('utf8').decode('utf8')
        value = self.unescape_tag_restrictions(value)
        # Some folks seem to be interpreting the docs quote marks as
        # literal for values.
        value = value.strip("'").strip('"')
        return value

    @classmethod
    def unescape_tag_restrictions(cls, value: str):
        for i, c in enumerate(cls.TAG_RESTRICTIONS_ESCAPE):
            value = value.replace(c, cls.TAG_RESTRICTIONS[i])
        return value

    @classmethod
    def get_tz(cls, tz):
        found = cls.TZ_ALIASES.get(tz)
        if found:
            return tzutil.gettz(found)
        return tzutil.gettz(tz.title())

    def get_default_schedule(self):
        raise NotImplementedError("use subclass")


class OffHour(Time):

    schema = type_schema(
        'offhour', rinherit=Time.schema, required=['offhour', 'default_tz'],
        offhour={'type': 'integer', 'minimum': 0, 'maximum': 23})
    time_type = "off"

    DEFAULT_HR = 19

    def get_default_schedule(self):
        default = {'tz': self.default_tz, self.time_type: [
            {'hour': self.data.get(
                "%shour" % self.time_type, self.DEFAULT_HR)}]}
        if self.weekends_only:
            default[self.time_type][0]['days'] = [4]
        elif self.weekends:
            default[self.time_type][0]['days'] = tuple(range(5))
        else:
            default[self.time_type][0]['days'] = tuple(range(7))
        return default


class OnHour(Time):

    schema = type_schema(
        'onhour', rinherit=Time.schema, required=['onhour', 'default_tz'],
        onhour={'type': 'integer', 'minimum': 0, 'maximum': 23})
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
            default[self.time_type][0]['days'] = tuple(range(5))
        else:
            default[self.time_type][0]['days'] = tuple(range(7))
        return default


class ScheduleParser:
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

    @staticmethod
    def raw_data(tag_value):
        """convert the tag to a dictionary, taking values as is

        This method name and purpose are opaque...  and not true.
        """
        data = {}
        pieces = []
        for p in tag_value.split(' '):
            pieces.extend(p.split(';'))
        # parse components
        for piece in pieces:
            kv = piece.split('=')
            # components must by key=value
            if not len(kv) == 2:
                continue
            key, value = kv
            data[key] = value
        return data

    def keys_are_valid(self, tag_value):
        """test that provided tag keys are valid"""
        for key in ScheduleParser.raw_data(tag_value):
            if key not in ('on', 'off', 'tz'):
                return False
        return True

    def parse(self, tag_value):
        # check the cache
        if tag_value in self.cache:
            return self.cache[tag_value]

        schedule = {}

        if not self.keys_are_valid(tag_value):
            return None
        # parse schedule components
        pieces = tag_value.split(';')
        for piece in pieces:
            kv = piece.split('=')
            # components must by key=value
            if not len(kv) == 2:
                return None
            key, value = kv
            if key != 'tz':
                if value != 'disabled':
                    value = self.parse_resource_schedule(value)
            if value is None:
                return None
            if value != 'disabled':
                schedule[key] = value

        # add default timezone, if none supplied or blank
        if not schedule.get('tz'):
            schedule['tz'] = self.default_schedule['tz']

        # cache
        self.cache[tag_value] = schedule
        return schedule

    @staticmethod
    def has_resource_schedule(tag_value, time_type):
        raw_data = ScheduleParser.raw_data(tag_value)
        # note time_type is set to 'on' or 'off' and raw_data is a dict
        return time_type in raw_data

    def parse_resource_schedule(self, lexeme):
        parsed = []
        exprs = brackets_removed(lexeme).split(',(')
        for e in exprs:
            tokens = parens_removed(e).split(',')
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
            return list(range(day_range[0], 7)) + list(range(day_range[1] + 1))
        return list(range(min(day_range), max(day_range) + 1))
