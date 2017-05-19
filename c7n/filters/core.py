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
Resource Filtering Logic
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime, timedelta
import fnmatch
import logging
import operator
import re

from dateutil.tz import tzutc
from dateutil.parser import parse
import jmespath
import ipaddress

from c7n.executor import ThreadPoolExecutor
from c7n.registry import PluginRegistry
from c7n.resolver import ValuesFrom
from c7n.utils import set_annotation, type_schema, parse_cidr


class FilterValidationError(Exception):
    pass


# Matching filters annotate their key onto objects
ANNOTATION_KEY = "c7n:MatchedFilters"


def glob_match(value, pattern):
    if not isinstance(value, basestring):
        return False
    return fnmatch.fnmatch(value, pattern)


def regex_match(value, regex):
    if not isinstance(value, basestring):
        return False
    # Note python 2.5+ internally cache regex
    # would be nice to use re2
    return bool(re.match(regex, value, flags=re.IGNORECASE))


def operator_in(x, y):
    return x in y


def operator_ni(x, y):
    return x not in y


OPERATORS = {
    'eq': operator.eq,
    'equal': operator.eq,
    'ne': operator.ne,
    'not-equal': operator.ne,
    'gt': operator.gt,
    'greater-than': operator.gt,
    'ge': operator.ge,
    'gte': operator.ge,
    'le': operator.le,
    'lte': operator.le,
    'lt': operator.lt,
    'less-than': operator.lt,
    'glob': glob_match,
    'regex': regex_match,
    'in': operator_in,
    'ni': operator_ni,
    'not-in': operator_ni,
    'contains': operator.contains}


class FilterRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(FilterRegistry, self).__init__(*args, **kw)
        self.register('value', ValueFilter)
        self.register('or', Or)
        self.register('and', And)
        self.register('not', Not)
        self.register('event', EventFilter)

    def parse(self, data, manager):
        results = []
        for d in data:
            results.append(self.factory(d, manager))
        return results

    def factory(self, data, manager=None):
        """Factory func for filters.

        data - policy config for filters
        manager - resource type manager (ec2, s3, etc)
        """

        # Make the syntax a little nicer for common cases.
        if isinstance(data, dict) and len(data) == 1 and 'type' not in data:
            if data.keys()[0] == 'or':
                return Or(data, self, manager)
            elif data.keys()[0] == 'and':
                return And(data, self, manager)
            elif data.keys()[0] == 'not':
                return Not(data, self, manager)
            return ValueFilter(data, manager).validate()
        if isinstance(data, basestring):
            filter_type = data
            data = {'type': data}
        else:
            filter_type = data.get('type')
        if not filter_type:
            raise FilterValidationError(
                "%s Invalid Filter %s" % (
                    self.plugin_type, data))
        filter_class = self.get(filter_type)
        if filter_class is not None:
            return filter_class(data, manager)
        else:
            raise FilterValidationError(
                "%s Invalid filter type %s" % (
                    self.plugin_type, data))


# Really should be an abstract base class (abc) or
# zope.interface

class Filter(object):

    executor_factory = ThreadPoolExecutor

    log = logging.getLogger('custodian.filters')

    metrics = ()
    permissions = ()
    schema = {'type': 'object'}

    def __init__(self, data, manager=None):
        self.data = data
        self.manager = manager

    def get_permissions(self):
        return self.permissions

    def validate(self):
        """validate filter config, return validation error or self"""
        return self

    def process(self, resources, event=None):
        """ Bulk process resources and return filtered set."""
        return filter(self, resources)


class Or(Filter):

    def __init__(self, data, registry, manager):
        super(Or, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(self.data.values()[0], manager)
        self.manager = manager

    def process(self, resources, event=None):
        if self.manager:
            return self.process_set(resources, event)
        return super(Or, self).process(resources, event)

    def __call__(self, r):
        """Fallback for older unit tests that don't utilize a query manager"""
        for f in self.filters:
            if f(r):
                return True
        return False

    def process_set(self, resources, event):
        resource_type = self.manager.get_model()
        resource_map = {r[resource_type.id]: r for r in resources}
        results = set()
        for f in self.filters:
            results = results.union([
                r[resource_type.id] for r in f.process(resources, event)])
        return [resource_map[r_id] for r_id in results]


class And(Filter):

    def __init__(self, data, registry, manager):
        super(And, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(self.data.values()[0], manager)

    def process(self, resources, events=None):
        for f in self.filters:
            resources = f.process(resources, events)
        return resources


class Not(Filter):

    def __init__(self, data, registry, manager):
        super(Not, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(self.data.values()[0], manager)
        self.manager = manager

    def process(self, resources, event=None):
        if self.manager:
            return self.process_set(resources, event)
        return super(Not, self).process(resources, event)

    def __call__(self, r):
        """Fallback for older unit tests that don't utilize a query manager"""

        # There is an implicit 'and' for self.filters
        # ~(A ^ B ^ ... ^ Z) = ~A v ~B v ... v ~Z
        for f in self.filters:
            if not f(r):
                return True
        return False

    def process_set(self, resources, event):
        resource_type = self.manager.get_model()
        resource_map = {r[resource_type.id]: r for r in resources}

        for f in self.filters:
            resources = f.process(resources, event)

        before = set(resource_map.keys())
        after = set([r[resource_type.id] for r in resources])
        results = before - after
        return [resource_map[r_id] for r_id in results]


class ValueFilter(Filter):
    """Generic value filter using jmespath
    """
    expr = None
    op = v = vtype = None

    schema = {
        'type': 'object',
        # Doesn't mix well with inherits that extend
        'additionalProperties': False,
        'required': ['type'],
        'properties': {
            # Doesn't mix well as enum with inherits that extend
            'type': {'enum': ['value']},
            'key': {'type': 'string'},
            'value_type': {'enum': [
                'age', 'integer', 'expiration', 'normalize', 'size',
                'cidr', 'cidr_size', 'swap', 'resource_count', 'expr']},
            'default': {'type': 'object'},
            'value_from': ValuesFrom.schema,
            'value': {'oneOf': [
                {'type': 'array'},
                {'type': 'string'},
                {'type': 'boolean'},
                {'type': 'number'},
                {'type': 'null'}]},
            'op': {'enum': OPERATORS.keys()}}}

    annotate = True

    def __init__(self, data, manager=None):
        super(ValueFilter, self).__init__(data, manager)
        self.expr = {}

    def _validate_resource_count(self):
        """ Specific validation for `resource_count` type

        The `resource_count` type works a little differently because it operates
        on the entire set of resources.  It:
          - does not require `key`
          - `value` must be a number
          - supports a subset of the OPERATORS list
        """
        for field in ('op', 'value'):
            if field not in self.data:
                raise FilterValidationError(
                    "Missing '%s' in value filter %s" % (field, self.data))

        if not (isinstance(self.data['value'], int) or
                isinstance(self.data['value'], list)):
            raise FilterValidationError(
                "`value` must be an integer in resource_count filter %s" % self.data)

        # I don't see how to support regex for this?
        if self.data['op'] not in OPERATORS or self.data['op'] == 'regex':
            raise FilterValidationError(
                "Invalid operator in value filter %s" % self.data)

        return self

    def validate(self):
        if len(self.data) == 1:
            return self

        # `resource_count` requires a slightly different schema than the rest of
        # the value filters because it operates on the full resource list
        if self.data.get('value_type') == 'resource_count':
            return self._validate_resource_count()

        if 'key' not in self.data:
            raise FilterValidationError(
                "Missing 'key' in value filter %s" % self.data)
        if 'value' not in self.data and 'value_from' not in self.data:
            raise FilterValidationError(
                "Missing 'value' in value filter %s" % self.data)
        if 'op' in self.data:
            if not self.data['op'] in OPERATORS:
                raise FilterValidationError(
                    "Invalid operator in value filter %s" % self.data)
            if self.data['op'] == 'regex':
                # Sanity check that we can compile
                try:
                    re.compile(self.data['value'])
                except re.error as e:
                    raise FilterValidationError(
                        "Invalid regex: %s %s" % (e, self.data))
        return self

    def __call__(self, i):
        if self.data.get('value_type') == 'resource_count':
            return self.process(i)

        matched = self.match(i)
        if matched and self.annotate:
            set_annotation(i, ANNOTATION_KEY, self.k)
        return matched

    def process(self, resources, event=None):
        # For the resource_count filter we operate on the full set of resources.
        if self.data.get('value_type') == 'resource_count':
            op = OPERATORS[self.data.get('op')]
            if op(len(resources), self.data.get('value')):
                return resources
            return []

        return super(ValueFilter, self).process(resources, event)

    def get_resource_value(self, k, i):
        if k.startswith('tag:'):
            tk = k.split(':', 1)[1]
            r = None
            for t in i.get("Tags", []):
                if t.get('Key') == tk:
                    r = t.get('Value')
                    break
        elif k in i:
            r = i.get(k)
        elif k not in self.expr:
            self.expr[k] = jmespath.compile(k)
            r = self.expr[k].search(i)
        else:
            r = self.expr[k].search(i)
        return r

    def match(self, i):
        if self.v is None and len(self.data) == 1:
            [(self.k, self.v)] = self.data.items()
        elif self.v is None:
            self.k = self.data.get('key')
            self.op = self.data.get('op')
            if 'value_from' in self.data:
                values = ValuesFrom(self.data['value_from'], self.manager)
                self.v = values.get_values()
            else:
                self.v = self.data.get('value')
            self.vtype = self.data.get('value_type')

        if i is None:
            return False

        # value extract
        r = self.get_resource_value(self.k, i)

        if self.op in ('in', 'not-in') and r is None:
            r = ()

        # value type conversion
        if self.vtype is not None:
            v, r = self.process_value_type(self.v, r, i)
        else:
            v = self.v

        # Value match
        if r is None and v == 'absent':
            return True
        elif r is not None and v == 'present':
            return True
        elif v == 'not-null' and r:
            return True
        elif v == 'empty' and not r:
            return True
        elif self.op:
            op = OPERATORS[self.op]
            try:
                return op(r, v)
            except TypeError:
                return False
        elif r == self.v:
            return True

        return False

    def process_value_type(self, sentinel, value, resource):
        if self.vtype == 'normalize' and isinstance(value, basestring):
            return sentinel, value.strip().lower()

        elif self.vtype == 'expr':
            return sentinel, self.get_resource_value(value, resource)

        elif self.vtype == 'integer':
            try:
                value = int(value.strip())
            except ValueError:
                value = 0
        elif self.vtype == 'size':
            try:
                return sentinel, len(value)
            except TypeError:
                return sentinel, 0
        elif self.vtype == 'swap':
            return value, sentinel
        elif self.vtype == 'age':
            if not isinstance(sentinel, datetime):
                sentinel = datetime.now(tz=tzutc()) - timedelta(sentinel)

            if not isinstance(value, datetime):
                # EMR bug when testing ages in EMR. This is due to
                # EMR not having more functionality.
                try:
                    value = parse(value, default=datetime.now(tz=tzutc()))
                except (AttributeError, TypeError, ValueError):
                    value = 0

            # Reverse the age comparison, we want to compare the value being
            # greater than the sentinel typically. Else the syntax for age
            # comparisons is intuitively wrong.
            return value, sentinel
        elif self.vtype == 'cidr':
            s = parse_cidr(sentinel)
            v = parse_cidr(value)
            if (isinstance(s, ipaddress._BaseAddress) and isinstance(v, ipaddress._BaseNetwork)):
                return v, s
            return s, v
        elif self.vtype == 'cidr_size':
            cidr = parse_cidr(value)
            if cidr:
                return sentinel, cidr.prefixlen
            return sentinel, 0

        # Allows for expiration filtering, for events in the future as opposed
        # to events in the past which age filtering allows for.
        elif self.vtype == 'expiration':
            if not isinstance(sentinel, datetime):
                sentinel = datetime.now(tz=tzutc()) + timedelta(sentinel)

            if not isinstance(value, datetime):
                try:
                    value = parse(value, default=datetime.now(tz=tzutc()))
                except (AttributeError, TypeError, ValueError):
                    value = 0

            return sentinel, value
        return sentinel, value


class AgeFilter(Filter):
    """Automatically filter resources older than a given date.
    """
    threshold_date = None

    # The name of attribute to compare to threshold; must override in subclass
    date_attribute = None

    schema = None

    def validate(self):
        if not self.date_attribute:
            raise NotImplementedError(
                "date_attribute must be overriden in subclass")
        return self

    def get_resource_date(self, i):
        v = i[self.date_attribute]
        if not isinstance(v, datetime):
            v = parse(v)
        if not v.tzinfo:
            v = v.replace(tzinfo=tzutc())
        return v

    def __call__(self, i):
        v = self.get_resource_date(i)
        if v is None:
            return False
        op = OPERATORS[self.data.get('op', 'greater-than')]

        if not self.threshold_date:

            days = self.data.get('days', 0)
            hours = self.data.get('hours', 0)
            minutes = self.data.get('minutes', 0)
            # Work around placebo issues with tz
            if v.tzinfo:
                n = datetime.now(tz=tzutc())
            else:
                n = datetime.now()
            self.threshold_date = n - timedelta(days=days, hours=hours, minutes=minutes)

        return op(self.threshold_date, v)


class EventFilter(ValueFilter):
    """Filter against a cloudwatch event associated to a resource type."""

    schema = type_schema('event', rinherit=ValueFilter.schema)

    def validate(self):
        if 'mode' not in self.manager.data:
            raise FilterValidationError(
                "Event filters can only be used with lambda policies")
        return self

    def process(self, resources, event=None):
        if event is None:
            return resources
        if self(event):
            return resources
        return []
