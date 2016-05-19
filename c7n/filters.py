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

from datetime import datetime, timedelta
import fnmatch
import logging
import operator
import re

from dateutil.tz import tzutc
from dateutil.parser import parse
import jmespath

from c7n.executor import ThreadPoolExecutor
from c7n.registry import PluginRegistry
from c7n.utils import set_annotation, type_schema


class FilterValidationError(Exception): pass


# Matching filters annotate their key onto objects
ANNOTATION_KEY = "MatchedFilters"


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
    'not-in': operator_ni}


class FilterRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(FilterRegistry, self).__init__(*args, **kw)
        self.register('value', ValueFilter)
        self.register('or', Or)
        self.register('and', And)
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
            return filter_class(data, manager).validate()
        else:
            raise FilterValidationError(
                "%s Invalid filter type %s" % (
                    self.plugin_type, data))


# Really should be an abstract base class (abc) or
# zope.interface

class Filter(object):

    executor_factory = ThreadPoolExecutor

    log = logging.getLogger('custodian.filters')

    schema = {'type': 'object'}

    def __init__(self, data, manager=None):
        self.data = data
        self.manager = manager

    def validate(self):
        """validate filter config, return validation error or self"""
        return self

    def process(self, resources, event=None):
        """ Bulk process resources and return filtered set."""
        return filter(self, resources)

    def __call__(self, instance):
        """ Process an individual resource."""
        raise NotImplementedError()


class Or(Filter):

    def __init__(self, data, registry, manager):
        super(Or, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(self.data.values()[0], manager)

    # TODO support resource set processing with or (will need identity
    # metadata per resource type), ala tags set_id or query metamodel branch
    def __call__(self, i):
        for f in self.filters:
            if f(i):
                return True
        return False


class And(Filter):

    def __init__(self, data, registry, manager):
        super(And, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(self.data.values()[0], manager)

    def __call__(self, i):
        for f in self.filters:
            if not f(i):
                return False
        return True


class ValueFilter(Filter):
    """Generic value filter using jmespath
    """
    expr = None
    op = v = None

    schema = {
        'type': 'object',
        # Doesn't mix well with inherits that extend
        'additionalProperties': False,
        'required': ['type'],
        'properties': {
            # Doesn't mix well as enum with inherits that extend
            'type': {'enum': ['value']},
            'key': {'type': 'string'},
            'value': {'oneOf': [
                {'type': 'array'},
                {'type': 'string'},
                {'type': 'boolean'},
                {'type': 'number'}]},
            'op': {'enum': OPERATORS.keys()}}}

    def validate(self):
        if len(self.data) == 1:
            return self
        if not 'key' in self.data:
            raise FilterValidationError(
                "Missing 'key' in value filter %s" % self.data)
        if not 'value' in self.data:
            raise FilterValidationError(
                "Missing 'value' in value filter %s" % self.data)
        if 'op' in self.data:
            if not self.data['op'] in OPERATORS:
                raise FilterValidationError(
                    "Invalid operator in value filter %s" %  self.data)
            if self.data['op'] == 'regex':
                # Sanity check that we can compile
                try:
                    re.compile(self.data['value'])
                except re.error as e:
                    raise FilterValidationError(
                        "Invalid regex: %s %s" % (e, self.data))
        return self

    def __call__(self, i):
        matched = self.match(i)
        if matched:
            set_annotation(i, ANNOTATION_KEY, self.k)
        return matched

    def match(self, i):
        if self.v is None and len(self.data) == 1:
            [(self.k, self.v)] = self.data.items()
        elif self.v is None:
            self.k = self.data.get('key')
            self.op = self.data.get('op')
            self.v = self.data.get('value')

        if i is None:
            return False

        # Value extract
        if self.k.startswith('tag:'):
            tk = self.k.split(':', 1)[1]
            r = None
            for t in i.get("Tags", []):
                if t.get('Key') == tk:
                    r = t.get('Value')
                    break
        elif not '.' in self.k and not '[' in self.k and not '(' in self.k:
            r = i.get(self.k)
        elif self.expr:
            r = self.expr.search(i)
        else:
            self.expr = jmespath.compile(self.k)
            r = self.expr.search(i)

        # Value match
        if r is None and self.v == 'absent':
            return True
        elif self.v == 'not-null' and r:
            return True
        elif self.op:
            op = OPERATORS[self.op]
            return op(r, self.v)
        elif r == self.v:
            return True
        return False


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
        return v

    def __call__(self, i):
        if not self.threshold_date:
            days = self.data.get('days', 60)
            n = datetime.now(tz=tzutc())
            self.threshold_date = n - timedelta(days)
        v = self.get_resource_date(i)
        return self.threshold_date > v


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
