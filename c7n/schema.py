# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
from collections import Counter
import json
import inspect
import logging

from jsonschema import Draft7Validator as JsonSchemaValidator
from jsonschema.exceptions import best_match

from c7n.policy import execution
from c7n.provider import clouds
from c7n.query import sources
from c7n.resources import load_available
from c7n.resolver import ValuesFrom
from c7n.filters.core import (
    ValueFilter,
    EventFilter,
    AgeFilter,
    ReduceFilter,
    OPERATORS,
    VALUE_TYPES,
)
from c7n.structure import StructureParser # noqa


def is_c7n_placeholder(instance):
    """Is this schema element a Custodian variable placeholder?

    Because policy validation can happen before we interpolate
    variable values, there are cases where we validate non-string
    types against variable placeholders. If a policy element is a string
    that starts and ends with curly braces, we should avoid failing
    failing type checks.
    """
    return (
        isinstance(instance, str)
        and instance.startswith('{')
        and instance.endswith('}')
    )


def validate(data, schema=None, resource_types=()):
    if schema is None:
        schema = generate(resource_types)
        JsonSchemaValidator.check_schema(schema)

    validator = JsonSchemaValidator(schema)
    errors = []
    for error in validator.iter_errors(data):
        try:
            error = specific_error(error)

            # ignore type checking errors against variable references that
            # haven't yet been expanded
            if error.validator == "type" and is_c7n_placeholder(error.instance):
                continue

            resp = policy_error_scope(error, data)
            name = (
                isinstance(error.instance, dict)
                and error.instance.get('name', 'unknown') or 'unknown'
            )
            return [resp, name]
        except Exception:
            logging.exception(
                "specific_error failed, traceback, followed by fallback")
            errors.append(error)
    if not errors:
        return check_unique(data) or []

    return list(filter(None, [
        errors[0],
        best_match(errors),
    ]))


def check_unique(data):
    counter = Counter([p['name'] for p in data.get('policies', [])])
    for k, v in list(counter.items()):
        if v == 1:
            counter.pop(k)
    if counter:
        return [ValueError(
            "Only one policy with a given name allowed, duplicates: {}".format(counter)),
            list(counter.keys())[0]]


def policy_error_scope(error, data):
    """Scope a schema error to its policy name and resource."""
    err_path = list(error.absolute_path)
    if err_path[0] != 'policies':
        return error
    pdata = data['policies'][err_path[1]]
    pdata.get('name', 'unknown')
    error.message = "Error on policy:{} resource:{}\n".format(
        pdata.get('name', 'unknown'), pdata.get('resource', 'unknown')) + error.message
    return error


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
            if '$ref' in v and v['$ref'].rsplit('/', 2)[1].endswith(r):
                found = idx
                break
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
            if ('$ref' in v and
                    v['$ref'].rsplit('/', 2)[-1].rsplit('.', 1)[-1] == t):
                found = idx
                break
            elif 'type' in v and t in v['properties'].get('type', {}).get('enum', []):
                found = idx
                break

        if found is not None:
            for e in error.context:
                for el in reversed(e.absolute_schema_path):
                    if isinstance(el, int):
                        if el == found:
                            return e
                        break
    return error


def _get_attr_schema():
    base_filters = [
        {'$ref': '#/definitions/filters/value'},
        {'$ref': '#/definitions/filters/valuekv'},
    ]
    any_of = []
    any_of.extend(base_filters)

    for op in ('and', 'or', 'not',):
        any_of.append(
            {
                'additional_properties': False,
                'properties': {
                    op: {
                        'type': 'array',
                        'items': {
                            'anyOf': base_filters
                        }
                    }
                },
                'type': 'object'
            }
        )

    attr_schema = {
        'items': {
            'anyOf': any_of
        },
        'type': 'array',
    }
    return attr_schema


def get_default_definitions(resource_defs):
    return {
        'resources': resource_defs,
        'string_dict': {
            "type": "object",
            "patternProperties": {
                "": {"type": "string"},
            },
        },
        'basic_dict': {
            "type": "object",
            "patternProperties": {
                "": {
                    'oneOf': [
                        {"type": "string"},
                        {"type": "boolean"},
                        {"type": "number"},
                    ],
                }
            },
        },
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
        'actions': {},
        'filters': {
            'value': ValueFilter.schema,
            'event': EventFilter.schema,
            'age': AgeFilter.schema,
            'reduce': ReduceFilter.schema,
            # Shortcut form of value filter as k=v
            'valuekv': {
                'type': 'object',
                'additionalProperties': {'oneOf': [{'type': 'number'}, {'type': 'null'},
                    {'type': 'array', 'maxItems': 0}, {'type': 'string'}, {'type': 'boolean'}]},
                'minProperties': 1,
                'maxProperties': 1},
        },
        'filters_common': {
            'list_item_attrs': _get_attr_schema(),
            'comparison_operators': {
                'enum': list(OPERATORS.keys())},
            'value_types': {'enum': VALUE_TYPES},
            'value_from': ValuesFrom.schema,
            'value': {'oneOf': [
                {'type': 'array'},
                {'type': 'string'},
                {'type': 'boolean'},
                {'type': 'number'},
                {'type': 'null'}]},
        },
        'policy': {
            'type': 'object',
            'required': ['name', 'resource'],
            'additionalProperties': False,
            'properties': {
                'name': {
                    'type': 'string',
                    'pattern': "^[A-z][A-z0-9]*(-[A-z0-9]+)*$"},
                'conditions': {
                    'type': 'array',
                    'items': {'anyOf': [
                        {'type': 'object', 'additionalProperties': False,
                         'properties': {'or': {
                             '$ref': '#/definitions/policy/properties/conditions'}}},
                        {'type': 'object', 'additionalProperties': False,
                         'properties': {'not': {
                             '$ref': '#/definitions/policy/properties/conditions'}}},
                        {'type': 'object', 'additionalProperties': False,
                         'properties': {'and': {
                             '$ref': '#/definitions/policy/properties/conditions'}}},
                        {'$ref': '#/definitions/filters/value'},
                        {'$ref': '#/definitions/filters/event'},
                        {'$ref': '#/definitions/filters/valuekv'}]}},
                # these should be deprecated for conditions
                'region': {'type': 'string'},
                'tz': {'type': 'string'},
                'start': {'format': 'date-time'},
                'end': {'format': 'date-time'},
                'resource': {'oneOf': [
                    {'type': 'string'},
                    {'type': 'array', 'items': {'type': 'string'}}]},
                'max-resources': {'anyOf': [
                    {'type': 'integer', 'minimum': 1},
                    {'$ref': '#/definitions/max-resources-properties'}
                ]},
                'max-resources-percent': {'type': 'number', 'minimum': 0, 'maximum': 100},
                'comment': {'type': 'string'},
                'comments': {'type': 'string'},
                'description': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'metadata': {'type': 'object'},
                'mode': {'$ref': '#/definitions/policy-mode'},
                'source': {'enum': list(sources.keys())},
                'actions': {
                    'type': 'array',
                },
                'filters': {
                    'type': 'array'
                },
                #
                # TODO: source queries should really move under
                # source. This was initially used for describe sources
                # to expose server side query mechanisms, however its
                # important to note it also prevents resource cache
                # utilization between policies that have different
                # queries.
                'query': {
                    'type': 'array', 'items': {'type': 'object'}}

            },
        },
        'policy-mode': {
            'anyOf': [e.schema for _, e in execution.items()],
        },
        'max-resources-properties': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'amount': {"type": 'integer', 'minimum': 1},
                'op': {'enum': ['or', 'and']},
                'percent': {'type': 'number', 'minimum': 0, 'maximum': 100}
            }
        }
    }


def generate(resource_types=()):
    resource_defs = {}
    definitions = get_default_definitions(resource_defs)

    resource_refs = []
    for cloud_name, cloud_type in sorted(clouds.items()):
        for type_name, resource_type in sorted(cloud_type.resources.items()):
            r_type_name = "%s.%s" % (cloud_name, type_name)
            if resource_types and r_type_name not in resource_types:
                if not resource_type.type_aliases:
                    continue
                elif not {"%s.%s" % (cloud_name, ralias) for ralias
                        in resource_type.type_aliases}.intersection(
                        resource_types):
                    continue

            aliases = []
            if resource_type.type_aliases:
                aliases.extend(["%s.%s" % (cloud_name, a) for a in resource_type.type_aliases])
                # aws gets legacy aliases with no cloud prefix
                if cloud_name == 'aws':
                    aliases.extend(resource_type.type_aliases)

            # aws gets additional alias for default name
            if cloud_name == 'aws':
                aliases.append(type_name)

            resource_refs.append(
                process_resource(
                    r_type_name,
                    resource_type,
                    resource_defs,
                    aliases,
                    definitions,
                    cloud_name
                ))

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
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

    # allow empty policies with lazy load
    if not resource_refs:
        schema['properties']['policies']['items'] = {'type': 'object'}
    return schema


def process_resource(
        type_name, resource_type, resource_defs, aliases=None,
        definitions=None, provider_name=None):

    r = resource_defs.setdefault(type_name, {'actions': {}, 'filters': {}})

    if getattr(resource_type, "get_schema", None):
        resource_type.get_schema(
            type_name, resource_defs, definitions, provider_name
        )
        return {'$ref': '#/definitions/resources/%s/policy' % type_name}

    action_refs = []
    for a in ElementSchema.elements(resource_type.action_registry):
        action_name = a.type
        if a.schema_alias:
            action_alias = "%s.%s" % (provider_name, action_name)
            if action_alias in definitions['actions']:

                if definitions['actions'][action_alias] != a.schema: # NOQA
                    msg = "Schema mismatch on type:{} action:{} w/ schema alias ".format(
                        type_name, action_name)
                    raise SyntaxError(msg)
            else:
                definitions['actions'][action_alias] = a.schema
            action_refs.append({'$ref': '#/definitions/actions/%s' % action_alias})
        else:
            r['actions'][action_name] = a.schema
            action_refs.append(
                {'$ref': '#/definitions/resources/%s/actions/%s' % (
                    type_name, action_name)})

    # one word action shortcuts
    action_refs.append(
        {'enum': list(resource_type.action_registry.keys())})

    filter_refs = []
    for f in ElementSchema.elements(resource_type.filter_registry):
        filter_name = f.type
        if filter_name == 'value':
            filter_refs.append({'$ref': '#/definitions/filters/value'})
            filter_refs.append({'$ref': '#/definitions/filters/valuekv'})
        elif filter_name == 'event':
            filter_refs.append({'$ref': '#/definitions/filters/event'})
        elif f.schema_alias:
            filter_alias = "%s.%s" % (provider_name, filter_name)
            if filter_alias in definitions['filters']:
                assert definitions['filters'][filter_alias] == f.schema, "Schema mismatch on filter w/ schema alias" # NOQA
            else:
                definitions['filters'][filter_alias] = f.schema
            filter_refs.append({'$ref': '#/definitions/filters/%s' % filter_alias})
            continue
        else:
            r['filters'][filter_name] = f.schema
            filter_refs.append(
                {'$ref': '#/definitions/resources/%s/filters/%s' % (
                    type_name, filter_name)})

    # one word filter shortcuts
    filter_refs.append(
        {'enum': list(resource_type.filter_registry.keys())})

    block_fref = '#/definitions/resources/%s/policy/allOf/1/properties/filters' % (
        type_name)
    filter_refs.extend([
        {'type': 'object', 'additionalProperties': False,
         'properties': {'or': {'$ref': block_fref}}},
        {'type': 'object', 'additionalProperties': False,
         'properties': {'and': {'$ref': block_fref}}},
        {'type': 'object', 'additionalProperties': False,
         'properties': {'not': {'$ref': block_fref}}}])

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

    if aliases:
        resource_policy['allOf'][1]['properties'][
            'resource']['enum'].extend(aliases)

    if type_name == 'ec2':
        resource_policy['allOf'][1]['properties']['query'] = {}

    r['policy'] = resource_policy
    return {'$ref': '#/definitions/resources/%s/policy' % type_name}


def resource_outline(provider=None):
    outline = {}
    for cname, ctype in sorted(clouds.items()):
        if provider and provider != cname:
            continue
        cresources = outline[cname] = {}
        for rname, rtype in sorted(ctype.resources.items()):
            cresources['%s.%s' % (cname, rname)] = rinfo = {}
            rinfo['filters'] = sorted(rtype.filter_registry.keys())
            rinfo['actions'] = sorted(rtype.action_registry.keys())
    return outline


def resource_vocabulary(cloud_name=None, qualify_name=True, aliases=True):
    vocabulary = {}
    resources = {}

    if aliases:
        vocabulary['aliases'] = {}

    for cname, ctype in clouds.items():
        if cloud_name is not None and cloud_name != cname:
            continue
        for rname, rtype in ctype.resources.items():
            if qualify_name:
                resources['%s.%s' % (cname, rname)] = rtype
            else:
                resources[rname] = rtype

    for type_name, resource_type in resources.items():
        classes = {'actions': {}, 'filters': {}, 'resource': resource_type}
        actions = []
        for cls in ElementSchema.elements(resource_type.action_registry):
            action_name = ElementSchema.name(cls)
            actions.append(action_name)
            classes['actions'][action_name] = cls

        filters = []
        for cls in ElementSchema.elements(resource_type.filter_registry):
            filter_name = ElementSchema.name(cls)
            filters.append(filter_name)
            classes['filters'][filter_name] = cls

        vocabulary[type_name] = {
            'filters': sorted(filters),
            'actions': sorted(actions),
            'classes': classes,
        }

        if aliases and resource_type.type_aliases:
            provider = type_name.split('.', 1)[0]
            for type_alias in resource_type.type_aliases:
                vocabulary['aliases'][
                    "{}.{}".format(provider, type_alias)] = vocabulary[type_name]
                if provider == 'aws':
                    vocabulary['aliases'][type_alias] = vocabulary[type_name]
            vocabulary[type_name]['resource_type'] = type_name

    vocabulary["mode"] = {}
    for mode_name, cls in execution.items():
        vocabulary["mode"][mode_name] = cls

    return vocabulary


class ElementSchema:
    """Utility functions for working with resource's filters and actions.
    """

    @staticmethod
    def elements(registry):
        """Given a resource registry return sorted de-aliased values.
        """
        seen = {}
        for k, v in registry.items():
            if k in ('and', 'or', 'not'):
                continue
            if v in seen:
                continue
            else:
                seen[ElementSchema.name(v)] = v
        return [seen[k] for k in sorted(seen)]

    @staticmethod
    def resolve(vocabulary, schema_path):
        """Given a resource vocabulary and a dotted path, resolve an element.
        """
        current = vocabulary
        frag = None
        if schema_path.startswith('.'):
            # The preprended '.' is an odd artifact
            schema_path = schema_path[1:]
        parts = schema_path.split('.')
        while parts:
            k = parts.pop(0)
            if frag:
                k = "%s.%s" % (frag, k)
                frag = None
                parts.insert(0, 'classes')
            elif k in clouds:
                frag = k
                if len(parts) == 1:
                    parts.append('resource')
                continue
            if k not in current:
                raise ValueError("Invalid schema path %s" % schema_path)
            current = current[k]
        return current

    @staticmethod
    def name(cls):
        """For a filter or action return its name."""
        return cls.schema['properties']['type']['enum'][0]

    @staticmethod
    def doc(cls):
        """Return 'best' formatted doc string for a given class.

        Walks up class hierarchy, skipping known bad. Returns
        empty string if no suitable doc string found.
        """
        # walk up class hierarchy for nearest
        # good doc string, skip known
        if cls.__doc__ is not None:
            return inspect.cleandoc(cls.__doc__)
        doc = None
        for b in cls.__bases__:
            if b in (ValueFilter, object):
                continue
            doc = b.__doc__ or ElementSchema.doc(b)
        if doc is not None:
            return inspect.cleandoc(doc)
        return ""

    @staticmethod
    def schema(definitions, cls):
        """Return a pretty'ified version of an element schema."""
        schema = isinstance(cls, type) and dict(cls.schema) or dict(cls)
        schema.pop('type', None)
        schema.pop('additionalProperties', None)
        return ElementSchema._expand_schema(schema, definitions)

    @staticmethod
    def _expand_schema(schema, definitions):
        """Expand references in schema to their full schema"""
        for k, v in list(schema.items()):
            if k == '$ref':
                # the value here is in the form of: '#/definitions/path/to/key'
                parts = v.split('/')
                if ['#', 'definitions'] != parts[0:2]:
                    raise ValueError("Invalid Ref %s" % v)
                current = definitions
                for p in parts[2:]:
                    if p not in current:
                        return None
                    current = current[p]
                return ElementSchema._expand_schema(current, definitions)
            elif isinstance(v, dict):
                schema[k] = ElementSchema._expand_schema(v, definitions)
        return schema


def pprint_schema_summary(vocabulary):
    providers = {}
    non_providers = {}

    for type_name, rv in vocabulary.items():
        if '.' not in type_name:
            non_providers[type_name] = len(rv)
        else:
            provider, _ = type_name.split('.', 1)
            stats = providers.setdefault(provider, {
                'resources': 0, 'actions': Counter(), 'filters': Counter()})
            stats['resources'] += 1
            for a in rv.get('actions'):
                stats['actions'][a] += 1
            for f in rv.get('filters'):
                stats['filters'][f] += 1

    for provider, stats in providers.items():
        print("%s:" % provider)
        print(" resource count: %d" % stats['resources'])
        print(" actions: %d" % len(stats['actions']))
        print(" filters: %d" % len(stats['filters']))

    for non_providers_type, length in non_providers.items():
        print("%s:" % non_providers_type)
        print(" count: %d" % length)


def json_dump(resource=None):
    load_available()
    print(json.dumps(generate(resource), indent=2))


if __name__ == '__main__':
    json_dump()
