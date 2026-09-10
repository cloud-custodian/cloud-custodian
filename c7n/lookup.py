# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import jmespath_search

import copy


class Skip:
    """Sentinel returned by Lookup.resolve_value to omit a value entirely."""

    __slots__ = ()

    def __repr__(self):
        return 'Lookup.SKIP'


class Lookup:
    RESOURCE_SOURCE = 'resource'

    SKIP = Skip()

    # A lookup needs a key, a fallback, or both. With a key it resolves against
    # the resource and falls back to 'default-value' when the path yields
    # nothing. With no key it is just the fallback -- which callers that pass a
    # name to resolve_value treat as a conditional default, writing it only
    # when that name is not already present on the resource.
    schema = {
        'type': 'object',
        'properties': {
            'type': {'type': 'string', 'enum': [RESOURCE_SOURCE]},
            'key': {'type': 'string'},
            'default-value': {},
        },
        'additionalProperties': False,
        'required': ['type'],
        'anyOf': [
            {'required': ['key']},
            {'required': ['default-value']},
        ]
    }

    @staticmethod
    def lookup_type(schema, default_schema=None):
        """Schema for a value that may be given directly or looked up.

        ``default_schema`` types the lookup's fallback, and defaults to
        ``schema``. Pass it when the fallback is narrower than the value --
        tag values, for instance, accept unquoted YAML scalars for backwards
        compatibility, but a fallback is always written as a string.
        """
        lookup_schema = copy.deepcopy(Lookup.schema)
        lookup_schema['properties']['default-value'] = (
            schema if default_schema is None else default_schema)

        return {
            'oneOf': [
                lookup_schema,
                schema
            ]
        }

    @staticmethod
    def resolve_value(spec, resource, name=None, current_names=()):
        """Resolve a value spec against a resource.

        Handles both lookup forms and plain scalars:

        - a scalar is returned unchanged
        - ``{type: resource, key: <jmespath>}`` resolves against the resource,
          falling back to ``default-value`` when the path yields nothing
        - ``{type: resource, default-value: <x>}`` (no key) is a conditional
          default: it resolves to ``x`` only when ``name`` is absent from
          ``current_names``, and to ``Lookup.SKIP`` otherwise.
        """
        if not Lookup.is_lookup(spec):
            return spec
        if 'key' not in spec and name in current_names:
            return Lookup.SKIP
        return Lookup.extract(spec, resource)

    @staticmethod
    def has_lookups(spec_map):
        """True if any value in the mapping is a lookup rather than a scalar."""
        return any(Lookup.is_lookup(v) for v in spec_map.values())

    @staticmethod
    def extract(source, data=None):
        if Lookup.is_lookup(source):
            return Lookup.get_value(source, data)
        else:
            return source

    @staticmethod
    def is_lookup(source):
        return isinstance(source, dict)

    @staticmethod
    def get_value(source, data=None):
        if source['type'] == Lookup.RESOURCE_SOURCE:
            return Lookup.get_value_from_resource(source, data)

    @staticmethod
    def get_value_from_resource(source, resource):
        if 'key' in source:
            value = jmespath_search(source['key'], resource)
            if value is not None:
                return value

        if 'default-value' not in source:
            raise Exception('Lookup for key, {}, returned None'.format(source['key']))
        else:
            return source['default-value']
