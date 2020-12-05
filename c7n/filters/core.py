# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Resource Filtering Logic
"""
import copy
import datetime
from datetime import timedelta
import fnmatch
import ipaddress
import logging
import operator
import re
import os

from dateutil.tz import tzutc
from dateutil.parser import parse
from distutils import version
from random import sample
import jmespath

from c7n.element import Element
from c7n.exceptions import PolicyValidationError
from c7n.registry import PluginRegistry
from c7n.resolver import ValuesFrom
from c7n.utils import set_annotation, type_schema, parse_cidr
from c7n.manager import iter_filters


class FilterValidationError(Exception):
    pass


# Matching filters annotate their key onto objects
ANNOTATION_KEY = "c7n:MatchedFilters"


def glob_match(value, pattern):
    if not isinstance(value, str):
        return False
    return fnmatch.fnmatch(value, pattern)


def regex_match(value, regex):
    if not isinstance(value, str):
        return False
    # Note python 2.5+ internally cache regex
    # would be nice to use re2
    return bool(re.match(regex, value, flags=re.IGNORECASE))


def regex_case_sensitive_match(value, regex):
    if not isinstance(value, str):
        return False
    # Note python 2.5+ internally cache regex
    # would be nice to use re2
    return bool(re.match(regex, value))


def operator_in(x, y):
    return x in y


def operator_ni(x, y):
    return x not in y


def difference(x, y):
    return bool(set(x).difference(y))


def intersect(x, y):
    return bool(set(x).intersection(y))


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
    'regex-case': regex_case_sensitive_match,
    'in': operator_in,
    'ni': operator_ni,
    'not-in': operator_ni,
    'contains': operator.contains,
    'difference': difference,
    'intersect': intersect}


VALUE_TYPES = [
    'age', 'integer', 'expiration', 'normalize', 'size',
    'cidr', 'cidr_size', 'swap', 'resource_count', 'expr',
    'unique_size', 'date', 'version']


class FilterRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(FilterRegistry, self).__init__(*args, **kw)
        self.register('value', ValueFilter)
        self.register('or', Or)
        self.register('and', And)
        self.register('not', Not)
        self.register('event', EventFilter)
        self.register('reduce', ReduceFilter)

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
            op = list(data.keys())[0]
            if op == 'or':
                return self['or'](data, self, manager)
            elif op == 'and':
                return self['and'](data, self, manager)
            elif op == 'not':
                return self['not'](data, self, manager)
            return ValueFilter(data, manager)
        if isinstance(data, str):
            filter_type = data
            data = {'type': data}
        else:
            filter_type = data.get('type')
        if not filter_type:
            raise PolicyValidationError(
                "%s Invalid Filter %s" % (
                    self.plugin_type, data))
        filter_class = self.get(filter_type)
        if filter_class is not None:
            return filter_class(data, manager)
        else:
            raise PolicyValidationError(
                "%s Invalid filter type %s" % (
                    self.plugin_type, data))


def trim_runtime(filters):
    """Remove runtime filters.

    Some filters can only be effectively evaluated at policy
    execution, ie. event filters.

    When evaluating conditions for dryrun or provisioning stages we
    remove them.
    """
    def remove_filter(f):
        block = f.get_block_parent()
        block.filters.remove(f)
        if isinstance(block, BooleanGroupFilter) and not len(block):
            remove_filter(block)

    for f in iter_filters(filters):
        if isinstance(f, EventFilter):
            remove_filter(f)


# Really should be an abstract base class (abc) or
# zope.interface

class Filter(Element):

    log = logging.getLogger('custodian.filters')

    def __init__(self, data, manager=None):
        self.data = data
        self.manager = manager

    def process(self, resources, event=None):
        """ Bulk process resources and return filtered set."""
        return list(filter(self, resources))

    def get_block_operator(self):
        """Determine the immediate parent boolean operator for a filter"""
        # Top level operator is `and`
        block = self.get_block_parent()
        if block.type in ('and', 'or', 'not'):
            return block.type
        return 'and'

    def get_block_parent(self):
        """Get the block parent for a filter"""
        block_stack = [self.manager]
        for f in self.manager.iter_filters(block_end=True):
            if f is None:
                block_stack.pop()
            elif f == self:
                return block_stack[-1]
            elif f.type in ('and', 'or', 'not'):
                block_stack.append(f)

    def merge_annotation(self, r, annotation_key, values):
        block_op = self.get_block_operator()
        if block_op in ('and', 'not'):
            r[self.matched_annotation_key] = intersect_list(
                values,
                r.get(self.matched_annotation_key))

        if not values and block_op != 'or':
            return


class BaseValueFilter(Filter):
    expr = None

    def __init__(self, data, manager=None):
        super(BaseValueFilter, self).__init__(data, manager)
        self.expr = {}

    def get_resource_value(self, k, i, regex=None):
        r = None
        if k.startswith('tag:'):
            tk = k.split(':', 1)[1]
            if 'Tags' in i:
                for t in i.get("Tags", []):
                    if t.get('Key') == tk:
                        r = t.get('Value')
                        break
            # GCP schema: 'labels': {'key': 'value'}
            elif 'labels' in i:
                r = i.get('labels', {}).get(tk, None)
            # GCP has a secondary form of labels called tags
            # as labels without values.
            # Azure schema: 'tags': {'key': 'value'}
            elif 'tags' in i:
                r = i.get('tags', {}).get(tk, None)
        elif k in i:
            r = i.get(k)
        elif k not in self.expr:
            self.expr[k] = jmespath.compile(k)
            r = self.expr[k].search(i)
        else:
            r = self.expr[k].search(i)

        if regex:
            r = ValueRegex(regex).get_resource_value(r)
        return r


def intersect_list(a, b):
    if b is None:
        return a
    elif a is None:
        return b
    res = []
    for x in a:
        if x in b:
            res.append(x)
    return res


class BooleanGroupFilter(Filter):

    def __init__(self, data, registry, manager):
        super(BooleanGroupFilter, self).__init__(data)
        self.registry = registry
        self.filters = registry.parse(list(self.data.values())[0], manager)
        self.manager = manager

    def validate(self):
        for f in self.filters:
            f.validate()
        return self

    def get_resource_type_id(self):
        resource_type = self.manager.get_model()
        return resource_type.id

    def __len__(self):
        return len(self.filters)

    def __bool__(self):
        return True


class Or(BooleanGroupFilter):

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
        rtype_id = self.get_resource_type_id()
        resource_map = {r[rtype_id]: r for r in resources}
        results = set()
        for f in self.filters:
            results = results.union([
                r[rtype_id] for r in f.process(resources, event)])
        return [resource_map[r_id] for r_id in results]


class And(BooleanGroupFilter):

    def process(self, resources, events=None):
        if self.manager:
            sweeper = AnnotationSweeper(self.get_resource_type_id(), resources)

        for f in self.filters:
            resources = f.process(resources, events)
            if not resources:
                break

        if self.manager:
            sweeper.sweep(resources)

        return resources


class Not(BooleanGroupFilter):

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
        rtype_id = self.get_resource_type_id()
        resource_map = {r[rtype_id]: r for r in resources}
        sweeper = AnnotationSweeper(rtype_id, resources)

        for f in self.filters:
            resources = f.process(resources, event)
            if not resources:
                break

        before = set(resource_map.keys())
        after = {r[rtype_id] for r in resources}
        results = before - after
        sweeper.sweep([])

        return [resource_map[r_id] for r_id in results]


class AnnotationSweeper:
    """Support clearing annotations set within a block filter.

    See https://github.com/cloud-custodian/cloud-custodian/issues/2116
    """
    def __init__(self, id_key, resources):
        self.id_key = id_key
        ra_map = {}
        resource_map = {}
        for r in resources:
            ra_map[r[id_key]] = {k: v for k, v in r.items() if k.startswith('c7n')}
            resource_map[r[id_key]] = r
        # We keep a full copy of the annotation keys to allow restore.
        self.ra_map = copy.deepcopy(ra_map)
        self.resource_map = resource_map

    def sweep(self, resources):
        for rid in set(self.ra_map).difference([
                r[self.id_key] for r in resources]):
            # Clear annotations if the block filter didn't match
            akeys = [k for k in self.resource_map[rid] if k.startswith('c7n')]
            for k in akeys:
                del self.resource_map[rid][k]
            # Restore annotations that may have existed prior to the block filter.
            self.resource_map[rid].update(self.ra_map[rid])


# The default LooseVersion will fail on comparing present strings, used
# in the value as shorthand for certain options.
class ComparableVersion(version.LooseVersion):
    def __eq__(self, other):
        try:
            return super(ComparableVersion, self).__eq__(other)
        except TypeError:
            return False


class ValueFilter(BaseValueFilter):
    """Generic value filter using jmespath
    """
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
            'value_type': {'$ref': '#/definitions/filters_common/value_types'},
            'default': {'type': 'object'},
            'value_regex': {'type': 'string'},
            'value_from': {'$ref': '#/definitions/filters_common/value_from'},
            'value': {'$ref': '#/definitions/filters_common/value'},
            'op': {'$ref': '#/definitions/filters_common/comparison_operators'}
        }
    }
    schema_alias = True
    annotate = True
    required_keys = {'value', 'key'}

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
                raise PolicyValidationError(
                    "Missing '%s' in value filter %s" % (field, self.data))

        if not (isinstance(self.data['value'], int) or
                isinstance(self.data['value'], list)):
            raise PolicyValidationError(
                "`value` must be an integer in resource_count filter %s" % self.data)

        # I don't see how to support regex for this?
        if (self.data['op'] not in OPERATORS or self.data['op'] in {'regex', 'regex-case'} or
                'value_regex' in self.data):
            raise PolicyValidationError(
                "Invalid operator in value filter %s" % self.data)

        return self

    def validate(self):
        if len(self.data) == 1:
            return self

        # `resource_count` requires a slightly different schema than the rest of
        # the value filters because it operates on the full resource list
        if self.data.get('value_type') == 'resource_count':
            return self._validate_resource_count()
        elif self.data.get('value_type') == 'date':
            if not parse_date(self.data.get('value')):
                raise PolicyValidationError(
                    "value_type: date with invalid date value:%s",
                    self.data.get('value', ''))
        if 'key' not in self.data and 'key' in self.required_keys:
            raise PolicyValidationError(
                "Missing 'key' in value filter %s" % self.data)
        if ('value' not in self.data and
                'value_from' not in self.data and
                'value' in self.required_keys):
            raise PolicyValidationError(
                "Missing 'value' in value filter %s" % self.data)
        if 'op' in self.data:
            if not self.data['op'] in OPERATORS:
                raise PolicyValidationError(
                    "Invalid operator in value filter %s" % self.data)
            if self.data['op'] in {'regex', 'regex-case'}:
                # Sanity check that we can compile
                try:
                    re.compile(self.data['value'])
                except re.error as e:
                    raise PolicyValidationError(
                        "Invalid regex: %s %s" % (e, self.data))
        if 'value_regex' in self.data:
            return self._validate_value_regex(self.data['value_regex'])

        return self

    def _validate_value_regex(self, regex):
        """Specific validation for `value_regex` type

        The `value_regex` type works a little differently.  In
        particular it doesn't support OPERATORS that perform
        operations on a list of values, specifically 'intersect',
        'contains', 'difference', 'in' and 'not-in'
        """
        # Sanity check that we can compile
        try:
            pattern = re.compile(regex)
            if pattern.groups != 1:
                raise PolicyValidationError(
                    "value_regex must have a single capturing group: %s" %
                    self.data)
        except re.error as e:
            raise PolicyValidationError(
                "Invalid value_regex: %s %s" % (e, self.data))
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
        return super(ValueFilter, self).get_resource_value(k, i, self.data.get('value_regex'))

    def match(self, i):
        if self.v is None and len(self.data) == 1:
            [(self.k, self.v)] = self.data.items()
        elif self.v is None and not hasattr(self, 'content_initialized'):
            self.k = self.data.get('key')
            self.op = self.data.get('op')
            if 'value_from' in self.data:
                values = ValuesFrom(self.data['value_from'], self.manager)
                self.v = values.get_values()
            else:
                self.v = self.data.get('value')
            self.content_initialized = True
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
        if self.vtype == 'normalize' and isinstance(value, str):
            return sentinel, value.strip().lower()

        elif self.vtype == 'expr':
            sentinel = self.get_resource_value(sentinel, resource)
            return sentinel, value

        elif self.vtype == 'integer':
            try:
                value = int(str(value).strip())
            except ValueError:
                value = 0
        elif self.vtype == 'size':
            try:
                return sentinel, len(value)
            except TypeError:
                return sentinel, 0
        elif self.vtype == 'unique_size':
            try:
                return sentinel, len(set(value))
            except TypeError:
                return sentinel, 0
        elif self.vtype == 'swap':
            return value, sentinel
        elif self.vtype == 'date':
            return parse_date(sentinel), parse_date(value)
        elif self.vtype == 'age':
            if not isinstance(sentinel, datetime.datetime):
                sentinel = datetime.datetime.now(tz=tzutc()) - timedelta(sentinel)
            value = parse_date(value)
            if value is None:
                # compatiblity
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
            if not isinstance(sentinel, datetime.datetime):
                sentinel = datetime.datetime.now(tz=tzutc()) + timedelta(sentinel)
            value = parse_date(value)
            if value is None:
                value = 0
            return sentinel, value

        # Allows for comparing version numbers, for things that you expect a minimum version number.
        elif self.vtype == 'version':
            s = ComparableVersion(sentinel)
            v = ComparableVersion(value)
            return s, v

        return sentinel, value


class AgeFilter(Filter):
    """Automatically filter resources older than a given date.

    **Deprecated** use a value filter with `value_type: age` which can be
    done on any attribute.
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
        if not isinstance(v, datetime.datetime):
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
                n = datetime.datetime.now(tz=tzutc())
            else:
                n = datetime.datetime.now()
            self.threshold_date = n - timedelta(days=days, hours=hours, minutes=minutes)

        return op(self.threshold_date, v)


class EventFilter(ValueFilter):
    """Filter a resource based on an event."""

    schema = type_schema('event', rinherit=ValueFilter.schema)
    schema_alias = True

    def validate(self):
        if 'mode' not in self.manager.data:
            raise PolicyValidationError(
                "Event filters can only be used with lambda policies in %s" % (
                    self.manager.data,))
        return self

    def process(self, resources, event=None):
        if event is None:
            return resources
        if self(event):
            return resources
        return []


def parse_date(v, tz=None):
    if v is None:
        return v

    tz = tz or tzutc()

    if isinstance(v, datetime.datetime):
        if v.tzinfo is None:
            return v.astimezone(tz)
        return v

    if isinstance(v, str):
        try:
            return parse(v).astimezone(tz)
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass

    # OSError on windows -- https://bugs.python.org/issue36439
    exceptions = (ValueError, OSError) if os.name == "nt" else (ValueError)

    if isinstance(v, (int, float, str)):
        try:
            v = datetime.datetime.fromtimestamp(float(v)).astimezone(tz)
        except exceptions:
            pass

    if isinstance(v, (int, float, str)):
        try:
            # try interpreting as milliseconds epoch
            v = datetime.datetime.fromtimestamp(float(v) / 1000).astimezone(tz)
        except exceptions:
            pass

    return isinstance(v, datetime.datetime) and v or None


class ValueRegex:
    """Allows filtering based on the output of a regex capture.
    This is useful for parsing data that has a weird format.

    Instead of comparing the contents of the 'resource value' with the 'value',
    it will instead apply the regex to contents of the 'resource value', and compare
    the result of the capture group defined in that regex with the 'value'.
    Therefore you must have a single capture group defined in the regex.

    If the regex doesn't find a match it will return 'None'

    Example of getting a datetime object to make an 'expiration' comparison::

    type: value
    value_regex: ".*delete_after=([0-9]{4}-[0-9]{2}-[0-9]{2}).*"
    key: "tag:company_mandated_metadata"
    value_type: expiration
    op: lte
    value: 0
    """

    def __init__(self, expr):
        self.expr = expr

    def get_resource_value(self, resource):
        if resource is None:
            return resource
        try:
            capture = re.match(self.expr, resource)
        except (ValueError, TypeError):
            return None
        if capture is None:  # regex didn't capture anything
            return None
        return capture.group(1)


class ReduceFilter(BaseValueFilter):
    """Generic reduce filter to group, sort, and limit your resources.

    This example will select the longest running instance from each ASG,
    then randomly choose 10% of those, maxing at 15 total instances.

    :example:

    .. code-block:: yaml

      - name: oldest-instance-by-asg
        resource: ec2
        filters:
          - "tag:aws:autoscaling:groupName": present
          - type: reduce
            group-by: "tag:aws:autoscaling:groupName"
            sort-by: "LaunchTime"
            order: asc
            limit: 1

    Or you might want to randomly select a 10 percent of your resources,
    but no more than 15.

    :example:

    .. code-block:: yaml

      - name: random-selection
        resource: ec2
        filters:
          - type: reduce
            order: randomize
            limit: 15
            limit-percent: 10

    """
    annotate = False

    schema = {
        'type': 'object',
        # Doesn't mix well with inherits that extend
        'additionalProperties': False,
        'required': ['type'],
        'properties': {
            # Doesn't mix well as enum with inherits that extend
            'type': {'enum': ['reduce']},
            'group-by': {
                'oneOf': [
                    {'type': 'string'},
                    {
                        'type': 'object',
                        'key': {'type': 'string'},
                        'value_type': {'enum': ['string', 'number', 'date']},
                        'value_regex': 'string',
                    },
                ]
            },
            'sort-by': {
                'oneOf': [
                    {'type': 'string'},
                    {
                        'type': 'object',
                        'key': {'type': 'string'},
                        'value_type': {'enum': ['string', 'number', 'date']},
                        'value_regex': 'string',
                    },
                ]
            },
            'order': {'enum': ['asc', 'desc', 'reverse', 'randomize']},
            'null-order': {'enum': ['first', 'last']},
            'limit': {'type': 'number', 'minimum': 0},
            'limit-percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
            'discard': {'type': 'number', 'minimum': 0},
            'discard-percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
        },
    }
    schema_alias = True

    def __init__(self, data, manager):
        super(ReduceFilter, self).__init__(data, manager)
        self.order = self.data.get('order', 'asc')
        self.group_by = self.get_sort_config('group-by')
        self.sort_by = self.get_sort_config('sort-by')

    def validate(self):
        # make sure the regexes compile
        if 'value_regex' in self.group_by:
            self._validate_value_regex(self.group_by['value_regex'])
        if 'value_regex' in self.sort_by:
            self._validate_value_regex(self.sort_by['value_regex'])
        return self

    def process(self, resources, event=None):
        groups = self.group(resources)

        # specified either of the sorting options, so sort
        if 'sort-by' in self.data or 'order' in self.data:
            groups = self.sort_groups(groups)

        # now apply any limits to the groups and concatenate
        return list(filter(None, self.limit(groups)))

    def group(self, resources):
        groups = {}
        for r in resources:
            v = self._value_to_sort(self.group_by, r)
            vstr = str(v)
            if vstr not in groups:
                groups[vstr] = {'sortkey': v, 'resources': []}
            groups[vstr]['resources'].append(r)
        return groups

    def get_sort_config(self, key):
        # allow `foo: bar` but convert to
        # `foo: {'key': bar}`
        d = self.data.get(key, {})
        if isinstance(d, str):
            d = {'key': d}
        d['null_sort_value'] = self.null_sort_value(d)
        return d

    def sort_groups(self, groups):
        for g in groups:
            groups[g]['resources'] = self.reorder(
                groups[g]['resources'],
                key=lambda r: self._value_to_sort(self.sort_by, r),
            )
        return groups

    def _value_to_sort(self, config, r):
        expr = config.get('key')
        vtype = config.get('value_type', 'string')
        vregex = config.get('value_regex')
        v = None

        try:
            # extract value based on jmespath
            if expr:
                v = self.get_resource_value(expr, r, vregex)

            if v is not None:
                # now convert to expected type
                if vtype == 'number':
                    v = float(v)
                elif vtype == 'date':
                    v = parse_date(v)
                else:
                    v = str(v)
        except (AttributeError, ValueError):
            v = None

        if v is None:
            v = config.get('null_sort_value')
        return v

    def null_sort_value(self, config):
        vtype = config.get('value_type', 'string')
        placement = self.data.get('null-order', 'last')

        if (placement == 'last' and self.order == 'desc') or (
            placement != 'last' and self.order != 'desc'
        ):
            # return a value that will sort first
            if vtype == 'number':
                return float('-inf')
            elif vtype == 'date':
                return datetime.datetime.min.replace(tzinfo=tzutc())
            return ''
        else:
            # return a value that will sort last
            if vtype == 'number':
                return float('inf')
            elif vtype == 'date':
                return datetime.datetime.max.replace(tzinfo=tzutc())
            return '\uffff'

    def limit(self, groups):
        results = []

        max = self.data.get('limit', 0)
        pct = self.data.get('limit-percent', 0)
        drop = self.data.get('discard', 0)
        droppct = self.data.get('discard-percent', 0)
        ordered = list(groups)
        if 'group-by' in self.data or 'order' in self.data:
            ordered = self.reorder(ordered, key=lambda r: groups[r]['sortkey'])
        for g in ordered:
            # discard X first
            if droppct > 0:
                n = int(droppct / 100 * len(groups[g]['resources']))
                if n > drop:
                    drop = n
            if drop > 0:
                groups[g]['resources'] = groups[g]['resources'][drop:]

            # then limit the remaining
            count = len(groups[g]['resources'])
            if pct > 0:
                count = int(pct / 100 * len(groups[g]['resources']))
            if max > 0 and max < count:
                count = max
            results.extend(groups[g]['resources'][0:count])
        return results

    def reorder(self, items, key=None):
        if self.order == 'randomize':
            return sample(items, k=len(items))
        elif self.order == 'reverse':
            return items[::-1]
        else:
            return sorted(items, key=key, reverse=(self.order == 'desc'))
