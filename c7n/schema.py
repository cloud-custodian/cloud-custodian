# Copyright 2016-2017 Capital One Services, LLC
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
Jsonschema validation of cloud custodian config.

We start with a walkthrough of the various class registries
of resource types and assemble and generate the schema.

We do some specialization to reduce overall schema size
via reference usage, although in some cases we prefer
copies, due to issues with inheritance via reference (
allowedProperties and enum extension).

All filters and actions are annotated with schema typically using
the utils.type_schema function.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import Counter
import json
import logging

from jsonschema import Draft4Validator as Validator
from jsonschema.exceptions import best_match

from c7n.policy import execution
from c7n.provider import clouds
from c7n.resources import load_resources
from c7n.filters import ValueFilter, EventFilter, AgeFilter


def validate(data, schema=None):
    if schema is None:
        schema = generate()
        Validator.check_schema(schema)

    validator = Validator(schema)

    errors = list(validator.iter_errors(data))

    if not errors:
        counter = Counter([p['name'] for p in data.get('policies')])
        dupes = []
        for k, v in counter.items():
            if v > 1:
                dupes.append(k)
        if dupes:
            return [ValueError(
                "Only one policy with a given name allowed, duplicates: %s" % (
                    ", ".join(dupes))), dupes[0]]
        return []
    try:
        resp = specific_error(errors[0])
        name = isinstance(
            errors[0].instance,
            dict) and errors[0].instance.get(
            'name',
            'unknown') or 'unknown'
        return [resp, name]
    except Exception:
        logging.exception(
            "specific_error failed, traceback, followed by fallback")

    return list(filter(None, [
        errors[0],
        best_match(validator.iter_errors(data)),
    ]))


def specific_error(error):
    """Try to find the best error for humans to resolve

    The jsonschema.exceptions.best_match error is based purely on a
    mix of a strong match (ie. not anyOf, oneOf) and schema depth,
    this often yields odd results that are semantically confusing,
    instead we can use a bit of structural knowledge of schema to
    provide better results.
    """
    if error.validator not in ('anyOf', 'oneOf'):
        return error

    r = t = None
    if isinstance(error.instance, dict):
        t = error.instance.get('type')
        r = error.instance.get('resource')

    if r is not None:
        found = None
        for idx, v in enumerate(error.validator_value):
            if v['$ref'].rsplit('/', 2)[1].endswith(r):
                found = idx
        if found is not None:
            # error context is a flat list of all validation
            # failures, we have to index back to the policy
            # of interest.
            for e in error.context:
                # resource policies have a fixed path from
                # the top of the schema
                if e.absolute_schema_path[4] == found:
                    return specific_error(e)
            return specific_error(error.context[idx])

    if t is not None:
        found = None
        for idx, v in enumerate(error.validator_value):
            if '$ref' in v and v['$ref'].endswith(t):
                found = idx
        if found is not None:
            # Try to walk back an element/type ref to the specific
            # error
            spath = list(error.context[0].absolute_schema_path)
            spath.reverse()
            slen = len(spath)
            if 'oneOf' in spath:
                idx = spath.index('oneOf')
            elif 'anyOf' in spath:
                idx = spath.index('anyOf')
            vidx = slen - idx
            for e in error.context:
                if e.absolute_schema_path[vidx] == found:
                    return e
    return error


def generate(resource_types=()):
    resource_defs = {}
    definitions = {
        'resources': resource_defs,
        'iam-statement': {
            'additionalProperties': False,
            'type': 'object',
            'properties': {
                'Sid': {'type': 'string'},
                'Effect': {'type': 'string', 'enum': ['Allow', 'Deny']},
                'Principal': {'anyOf': [
                    {'type': 'string'},
                    {'type': 'object'}, {'type': 'array'}]},
                'NotPrincipal': {'anyOf': [{'type': 'object'}, {'type': 'array'}]},
                'Action': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'NotAction': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'Resource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'NotResource': {'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                'Condition': {'type': 'object'}
            },
            'required': ['Sid', 'Effect'],
            'oneOf': [
                {'required': ['Principal', 'Action', 'Resource']},
                {'required': ['NotPrincipal', 'Action', 'Resource']},
                {'required': ['Principal', 'NotAction', 'Resource']},
                {'required': ['NotPrincipal', 'NotAction', 'Resource']},
                {'required': ['Principal', 'Action', 'NotResource']},
                {'required': ['NotPrincipal', 'Action', 'NotResource']},
                {'required': ['Principal', 'NotAction', 'NotResource']},
                {'required': ['NotPrincipal', 'NotAction', 'NotResource']}
            ]
        },
        'filters': {
            'value': ValueFilter.schema,
            'event': EventFilter.schema,
            'age': AgeFilter.schema,
            # Shortcut form of value filter as k=v
            'valuekv': {
                'type': 'object',
                'minProperties': 1,
                'maxProperties': 1},
        },

        'policy': {
            'type': 'object',
            'required': ['name', 'resource'],
            'additionalProperties': False,
            'properties': {
                'name': {
                    'type': 'string',
                    'pattern': "^[A-z][A-z0-9]*(-[A-z0-9]+)*$"},
                'region': {'type': 'string'},
                'tz': {'type': 'string'},
                'start': {'format': 'date-time'},
                'end': {'format': 'date-time'},
                'resource': {'type': 'string'},
                'max-resources': {'type': 'integer', 'minimum': 1},
                'max-resources-percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
                'comment': {'type': 'string'},
                'comments': {'type': 'string'},
                'description': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'mode': {'$ref': '#/definitions/policy-mode'},
                'source': {'enum': ['describe', 'config']},
                'actions': {
                    'type': 'array',
                },
                'filters': {
                    'type': 'array'
                },
                #
                # unclear if this should be allowed, it kills resource
                # cache coherency between policies, and we need to
                # generalize server side query mechanisms, currently
                # this only for ec2 instance queries. limitations
                # in json schema inheritance prevent us from doing this
                # on a type specific basis http://goo.gl/8UyRvQ
                'query': {
                    'type': 'array', 'items': {
                        'type': 'object',
                        'minProperties': 1,
                        'maxProperties': 1}}
            },
        },
        'policy-mode': {
            'anyOf': [e.schema for _, e in execution.items()],
        }
    }

    resource_refs = []
    for cloud_name, cloud_type in clouds.items():
        for type_name, resource_type in cloud_type.resources.items():
            if resource_types and type_name not in resource_types:
                continue
            alias_name = None
            r_type_name = "%s.%s" % (cloud_name, type_name)
            if cloud_name == 'aws':
                alias_name = type_name
            resource_refs.append(
                process_resource(r_type_name, resource_type, resource_defs, alias_name))

    schema = {
        '$schema': 'http://json-schema.org/schema#',
        'id': 'http://schema.cloudcustodian.io/v0/custodian.json',
        'definitions': definitions,
        'type': 'object',
        'required': ['policies'],
        'additionalProperties': False,
        'properties': {
            'vars': {'type': 'object'},
            'policies': {
                'type': 'array',
                'additionalItems': False,
                'items': {'anyOf': resource_refs}
            }
        }
    }

    return schema


def process_resource(type_name, resource_type, resource_defs, alias_name=None):
    r = resource_defs.setdefault(type_name, {'actions': {}, 'filters': {}})

    seen_actions = set()  # Aliases get processed once
    action_refs = []
    for action_name, a in resource_type.action_registry.items():
        if a in seen_actions:
            continue
        else:
            seen_actions.add(a)
        r['actions'][action_name] = a.schema
        action_refs.append(
            {'$ref': '#/definitions/resources/%s/actions/%s' % (
                type_name, action_name)})

    # one word action shortcuts
    action_refs.append(
        {'enum': list(resource_type.action_registry.keys())})

    nested_filter_refs = []
    filters_seen = set()
    for k, v in sorted(resource_type.filter_registry.items()):
        if v in filters_seen:
            continue
        else:
            filters_seen.add(v)
        nested_filter_refs.append(
            {'$ref': '#/definitions/resources/%s/filters/%s' % (
                type_name, k)})
    nested_filter_refs.append(
        {'$ref': '#/definitions/filters/valuekv'})

    filter_refs = []
    filters_seen = set()  # for aliases
    for filter_name, f in sorted(resource_type.filter_registry.items()):
        if f in filters_seen:
            continue
        else:
            filters_seen.add(f)

        if filter_name in ('or', 'and', 'not'):
            continue
        elif filter_name == 'value':
            r['filters'][filter_name] = {
                '$ref': '#/definitions/filters/value'}
            r['filters']['valuekv'] = {
                '$ref': '#/definitions/filters/valuekv'}
        elif filter_name == 'event':
            r['filters'][filter_name] = {
                '$ref': '#/definitions/filters/event'}
        else:
            r['filters'][filter_name] = f.schema
        filter_refs.append(
            {'$ref': '#/definitions/resources/%s/filters/%s' % (
                type_name, filter_name)})
    filter_refs.append(
        {'$ref': '#/definitions/filters/valuekv'})

    # one word filter shortcuts
    filter_refs.append(
        {'enum': list(resource_type.filter_registry.keys())})

    resource_policy = {
        'allOf': [
            {'$ref': '#/definitions/policy'},
            {'properties': {
                'resource': {'enum': [type_name]},
                'filters': {
                    'type': 'array',
                    'items': {'anyOf': filter_refs}},
                'actions': {
                    'type': 'array',
                    'items': {'anyOf': action_refs}}}},
        ]
    }

    if alias_name:
        resource_policy['allOf'][1]['properties'][
            'resource']['enum'].append(alias_name)

    if type_name == 'ec2':
        resource_policy['allOf'][1]['properties']['query'] = {}

    r['policy'] = resource_policy
    return {'$ref': '#/definitions/resources/%s/policy' % type_name}


def resource_vocabulary(cloud_name=None, qualify_name=True):
    vocabulary = {}
    resources = {}

    for cname, ctype in clouds.items():
        if cloud_name is not None and cloud_name != cname:
            continue
        for rname, rtype in ctype.resources.items():
            if qualify_name:
                resources['%s.%s' % (cname, rname)] = rtype
            else:
                resources[rname] = rtype

    for type_name, resource_type in resources.items():
        classes = {'actions': {}, 'filters': {}}
        actions = []
        for action_name, cls in resource_type.action_registry.items():
            actions.append(action_name)
            classes['actions'][action_name] = cls

        filters = []
        for filter_name, cls in resource_type.filter_registry.items():
            filters.append(filter_name)
            classes['filters'][filter_name] = cls

        vocabulary[type_name] = {
            'filters': sorted(filters),
            'actions': sorted(actions),
            'classes': classes,
        }
    return vocabulary


def summary(vocabulary):
    print("resource count: %d" % len(vocabulary))
    action_count = filter_count = 0

    common_actions = set(['notify', 'invoke-lambda'])
    common_filters = set(['value', 'and', 'or', 'event'])

    for rv in vocabulary.values():
        action_count += len(
            set(rv.get('actions', ())).difference(common_actions))
        filter_count += len(
            set(rv.get('filters', ())).difference(common_filters))
    print("unique actions: %d" % action_count)
    print("common actions: %d" % len(common_actions))
    print("unique filters: %d" % filter_count)
    print("common filters: %s" % len(common_filters))


def json_dump(resource=None):
    load_resources()
    print(json.dumps(generate(resource), indent=2))


if __name__ == '__main__':
    json_dump()
