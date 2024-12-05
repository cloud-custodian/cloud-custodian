# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import jmespath_search

import copy


class Lookup:
    RESOURCE_SOURCE = 'resource'

    schema = {
        'type': 'object',
        'oneOf': [
            {
                'properties': {
                    'type': {'type': 'string', 'enum': [RESOURCE_SOURCE]},
                    'key': {'type': 'string'}
                },
                'additionalProperties': False,
                'required': ['type', 'key']
            }
        ]
    }

    @staticmethod
    def lookup_type(schema):
        lookup_schema = copy.deepcopy(Lookup.schema)
        for lookup in lookup_schema['oneOf']:
            lookup['properties']['default-value'] = schema

        return {
            'oneOf': [
                lookup_schema,
                schema
            ]
        }

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
        value = jmespath_search(source['key'], resource)

        if value is not None:
            return value
        if 'default-value' not in source:
            raise Exception('Lookup for key, {}, returned None'.format(source['key']))
        else:
            return source['default-value']
