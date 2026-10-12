# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager, resources
from c7n.query import TypeInfo
from c7n.utils import local_session


@resources.register('boto-resource')
class BotoResource(ResourceManager):
    """Reflective PoC resource manager for arbitrary boto3 client list methods.

    This manager allows policies to dynamically enumerate resources from AWS
    services that do not yet have first-class Cloud Custodian resource support.

    Example
    -------
    .. code-block:: yaml

        policies:
          - name: duck-db-instances
            resource: boto-resource
            service: cloudduck
            method: list_instances

    Optional keys:
      - ``params``: dict of kwargs passed to the boto client call/paginator.
      - ``result_key``: explicit response key containing the list of resources.
      - ``id-field``: resource field used by ``get_resources`` lookups.
    """

    filter_registry = FilterRegistry('boto-resource.filters')
    action_registry = ActionRegistry('boto-resource.actions')

    class resource_type(TypeInfo):
        service = 'boto-resource'
        id = 'id'
        name = 'id'
        cfn_type = None
        config_type = None

    @classmethod
    def has_arn(cls):
        """Indicate this pseudo-resource does not provide generic ARN support."""
        return False

    @classmethod
    def get_schema(cls, type_name, resource_defs, definitions, provider_name):
        """Register dynamic policy schema for ``boto-resource``.

        Ensures top-level policy keys (``service``, ``method``, etc.) are
        recognized by both the global policy schema and this resource policy.
        """
        # NOTE: this is intentionally minimal and permissive for PoC use.
        r = resource_defs.setdefault(type_name, {'actions': {}, 'filters': {}})

        # The base policy schema has additionalProperties: false, so custom
        # top-level keys must be declared there as well.
        definitions['policy']['properties'].setdefault(
            'service', {'type': 'string', 'minLength': 1})
        definitions['policy']['properties'].setdefault(
            'method', {'type': 'string', 'minLength': 1})
        definitions['policy']['properties'].setdefault(
            'params', {'type': 'object'})
        definitions['policy']['properties'].setdefault(
            'result_key', {'type': 'string'})
        definitions['policy']['properties'].setdefault(
            'id-field', {'type': 'string'})

        resource_enum = [type_name]
        if provider_name == 'aws' and '.' in type_name:
            resource_enum.append(type_name.split('.', 1)[1])

        r['policy'] = {
            'allOf': [
                {'$ref': '#/definitions/policy'},
                {'properties': {
                    'resource': {'enum': resource_enum},
                    'service': {'type': 'string', 'minLength': 1},
                    'method': {'type': 'string', 'minLength': 1},
                    'params': {'type': 'object'},
                    'result_key': {'type': 'string'},
                    'id-field': {'type': 'string'},
                    'filters': {'type': 'array'},
                    'actions': {'type': 'array', 'maxItems': 0},
                },
                 'required': ['service', 'method']}
            ]
        }

        # defs are expected in schema output shape.
        r.setdefault('actions', {})
        r.setdefault('filters', {})

    def get_resource_manager(self, resource_type, data=None):
        """Return resource managers, with special-case self-resolution.

        The base implementation resolves managers through provider resource maps.
        For dynamic self-references to ``boto-resource`` we can directly create a
        new ``BotoResource`` instance.
        """
        # Base impl attempts provider map lookup/load, which is unnecessary for
        # self-references in this dynamic pseudo resource.
        if resource_type in ('boto-resource', 'aws.boto-resource'):
            return self.__class__(self.ctx, data or self.data)
        return super(BotoResource, self).get_resource_manager(resource_type, data=data)

    def get_model(self):
        """Return a minimal runtime TypeInfo derived from policy configuration."""
        id_field = self.data.get('id-field', 'id')
        return type('BotoTypeInfo', (TypeInfo,), {
            'service': self.data.get('service'),
            'name': id_field,
            'id': id_field,
            'arn': False,
            'dimension': None,
        })

    def _extract_resources(self, result):
        """Extract a list of resources from a boto response payload.

        Behavior:
          1. If response is already a list, return it.
          2. If ``result_key`` is set, return ``response[result_key]`` when list.
          3. Otherwise return the first list-valued key (excluding metadata).
        """
        if isinstance(result, list):
            return result

        if not isinstance(result, dict):
            return []

        result_key = self.data.get('result_key')
        if result_key:
            values = result.get(result_key, [])
            return values if isinstance(values, list) else []

        # Best-effort reflective extraction: first list-shaped payload member.
        for k, v in result.items():
            if k == 'ResponseMetadata':
                continue
            if isinstance(v, list):
                return v

        return []

    def _fetch_resources(self):
        """Call the configured boto client method and return enumerated resources.

        Uses a paginator when available, otherwise performs a single method call.
        """
        client = local_session(self.session_factory).client(self.data['service'])
        method_name = self.data['method']
        params = self.data.get('params', {})

        if client.can_paginate(method_name):
            paginator = client.get_paginator(method_name)
            resources = []
            for page in paginator.paginate(**params):
                resources.extend(self._extract_resources(page))
            return resources

        method = getattr(client, method_name)
        return self._extract_resources(method(**params))

    def resources(self):
        """Enumerate and filter resources for policy execution."""
        return self.filter_resources(self._fetch_resources())

    def _get_id_field(self, resources):
        """Resolve the identifier key used for ``get_resources`` lookups."""
        id_field = self.data.get('id-field')
        if id_field:
            return id_field

        if not resources or not isinstance(resources[0], dict):
            return None

        for candidate in ('id', 'Id', 'arn', 'Arn', 'name', 'Name'):
            if candidate in resources[0]:
                return candidate

        return None

    def get_resources(self, resource_ids):
        """Return resources whose identifier field matches ``resource_ids``.

        This PoC implementation re-enumerates via ``_fetch_resources`` and then
        performs in-memory filtering.
        """
        resources = self._fetch_resources()
        id_field = self._get_id_field(resources)
        if not id_field:
            return []

        resource_id_set = set(resource_ids)
        return [r for r in resources if isinstance(r, dict) and r.get(id_field) in resource_id_set]
