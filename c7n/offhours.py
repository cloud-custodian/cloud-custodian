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
        tz = self.get_local_tz(parts)
        if not tz:
            return False
        
        now = datetime.datetime.now(tz).replace(
            minute=0, second=0, microsecond=0)

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
    

class OffHour(Time):

    schema = type_schema(
        'offhour', rinherit=Time.schema, required=['offhour', 'default_tz'],
        offhour={'type': 'integer', 'minimum': 0, 'maximum': 24})

    def get_sentinel_time(self, tz):
        t = super(OffHour, self).get_sentinel_time(tz)
        return t.replace(hour=self.data.get('offhour', DEFAULT_OFFHOUR))

                         
class OnHour(Time):

    schema = type_schema(
        'onhour', rinherit=Time.schema, required=['onhour', 'default_tz'],
        onhour={'type': 'integer', 'minimum': 0, 'maximum': 24})

    def get_sentinel_time(self, tz):
        t = super(OnHour, self).get_sentinel_time(tz)
        return t.replace(hour=self.data.get('onhour', DEFAULT_ONHOUR))

    
    

