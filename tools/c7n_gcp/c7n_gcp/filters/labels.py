# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from c7n.utils import type_schema
from c7n.filters import Filter, FilterValidationError
from c7n.filters.offhours import Time

DEFAULT_TAG = "custodian_status"


class LabelActionFilter(Filter):
    """Filter resources for label specified future action

    Filters resources by a 'custodian_status' label which specifies a future
    date for an action.

    The filter parses the label values looking for an 'op@date'
    string. The date is parsed and compared to do today's date, the
    filter succeeds if today's date is gte to the target date.

    The optional 'skew' parameter provides for incrementing today's
    date a number of days into the future. An example use case might
    be sending a final notice email a few days before terminating an
    instance, or snapshotting a volume prior to deletion.

    The optional 'skew_hours' parameter provides for incrementing the current
    time a number of hours into the future.

    Optionally, the 'tz' parameter can get used to specify the timezone
    in which to interpret the clock (default value is 'utc')

    :example:

    .. code-block :: yaml

       policies:
        - name: vm-stop-marked
          resource: gcp.instance
          filters:
            - type: marked-for-op
              # The default label used is custodian_status
              # but that is configurable
              label: custodian_status
              op: stop
              # Another optional label is skew
              tz: utc


    """
    schema = type_schema(
        'marked-for-op',
        label={'type': 'string'},
        tz={'type': 'string'},
        skew={'type': 'number', 'minimum': 0},
        skew_hours={'type': 'number', 'minimum': 0},
        op={'type': 'string'})

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise FilterValidationError(
                "Invalid marked-for-op op:%s in %s" % (op, self.manager.data))

        tz = Time.get_tz(self.data.get('tz', 'utc'))
        if not tz:
            raise FilterValidationError(
                "Invalid timezone specified '%s' in %s" % (
                    self.data.get('tz'), self.manager.data))
        self.valid_actions = sorted(
            self.manager.action_registry.keys(), key=lambda k: len(k), reverse=True)
        return self

    def process(self, resources, event=None):
        self.label = self.data.get('label', DEFAULT_TAG)
        self.op = self.data.get('op', 'stop')
        self.skew = self.data.get('skew', 0)
        self.skew_hours = self.data.get('skew_hours', 0)
        self.tz = Time.get_tz(self.data.get('tz', 'utc'))
        return super(LabelActionFilter, self).process(resources, event)

    def parse(self, v: str):
        remainder, action_date = v.rsplit('-', 1)
        found = False
        msg = ""
        for a in self.valid_actions:
            if remainder.endswith(a):
                found = a
                msg = remainder[:-len(a) - 1]
                break
        return msg, found, action_date

    def __call__(self, i):
        v = i.get('labels', {}).get(self.label, None)

        if v is None:
            return False
        if '-' not in v or '_' not in v:
            return False

        _, action, action_date_str = self.parse(v)

        if action != self.op or not action:
            return False

        try:
            action_date = datetime.strptime(action_date_str, '%Y_%m_%d__%H_%M')
        except Exception:
            self.log.error("could not parse label:%s value:%s on %s" % (
                self.label, v, i['name']))
            return False

        # current_date must match timezones with the parsed date string
        if action_date.tzinfo:
            action_date = action_date.astimezone(self.tz)
            current_date = datetime.now(tz=self.tz)
        else:
            current_date = datetime.now()

        return current_date >= (action_date - timedelta(days=self.skew, hours=self.skew_hours))
