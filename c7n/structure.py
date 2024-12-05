# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json

from c7n.exceptions import PolicyValidationError


class StructureParser:
    """Provide fast validation and inspection of a policy file.

    Intent is to provide more humane validation for top level errors
    instead of printing full schema as error message.
    """
    allowed_file_keys = {'vars', 'policies'}
    required_policy_keys = {'name', 'resource'}
    allowed_policy_keys = {'name', 'resource', 'title', 'description', 'mode',
         'tags', 'max-resources', 'metadata', 'query',
         'filters', 'actions', 'source', 'conditions',
         # legacy keys subject to deprecation.
         'region', 'start', 'end', 'tz', 'max-resources-percent',
         'comments', 'comment'}

    def validate(self, data):
        if not isinstance(data, dict):
            raise PolicyValidationError((
                "Policy file top level data structure "
                "should be a mapping/dict, instead found:%s") % (
                    type(data).__name__))
        dkeys = set(data.keys())

        extra = dkeys.difference(self.allowed_file_keys)
        if extra:
            raise PolicyValidationError((
                'Policy files top level keys are %s, found extra: %s' % (
                    ', '.join(self.allowed_file_keys),
                    ', '.join(extra))))

        if 'policies' not in data:
            raise PolicyValidationError("`policies` list missing")

        pdata = data.get('policies', [])
        if not isinstance(pdata, list):
            raise PolicyValidationError((
                '`policies` key should be an array/list found: %s' % (
                    type(pdata).__name__)))
        for p in pdata:
            self.validate_policy(p)

    def validate_policy(self, p):
        if not isinstance(p, dict):
            raise PolicyValidationError((
                'policy must be a dictionary/mapping found:%s policy:\n %s' % (
                    type(p).__name__, json.dumps(p, indent=2))))
        pkeys = set(p)
        if self.required_policy_keys.difference(pkeys):
            raise PolicyValidationError(
                'policy missing required keys (name, resource) data:\n %s' % (
                    json.dumps(p, indent=2)))
        if pkeys.difference(self.allowed_policy_keys):
            raise PolicyValidationError(
                'policy:%s has unknown keys: %s' % (
                    p['name'], ','.join(pkeys.difference(self.allowed_policy_keys))))
        if "mode" in p:
            mode = p["mode"]
            if not isinstance(mode, dict) or "type" not in mode:
                raise PolicyValidationError("invalid `mode` declaration")
        if not isinstance(p.get('filters', []), (list, type(None))):
            raise PolicyValidationError((
                'policy:%s must use a list for filters found:%s' % (
                    p['name'], type(p['filters']).__name__)))
        element_types = (dict, str)
        for f in p.get('filters', ()) or []:
            if not isinstance(f, element_types):
                raise PolicyValidationError((
                    'policy:%s filter must be a mapping/dict found:%s' % (
                        p.get('name', 'unknown'), type(f).__name__)))
        if not isinstance(p.get('actions', []), (list, type(None))):
            raise PolicyValidationError((
                'policy:%s must use a list for actions found:%s' % (
                    p.get('name', 'unknown'), type(p['actions']).__name__)))
        for a in p.get('actions', ()) or []:
            if not isinstance(a, element_types):
                raise PolicyValidationError((
                    'policy:%s action must be a mapping/dict found:%s' % (
                        p.get('name', 'unknown'), type(a).__name__)))

        if isinstance(p.get('resource', ''), list):
            if len({pr.split('.')[0] for pr in p['resource']}) > 1:
                raise PolicyValidationError((
                    "policy:%s multi resource is only allowed with a single provider" % (
                        p.get('name', 'unknown'))))

    def get_resource_types(self, data):
        resources = set()
        for p in data.get('policies', []):
            rtype = p['resource']
            if isinstance(rtype, list):
                resources.update(rtype)
                continue
            elif '.' not in rtype:
                rtype = 'aws.%s' % rtype
            resources.add(rtype)
        return resources
