# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .core import Filter

from c7n.exceptions import PolicyValidationError
from c7n.loader import PolicyLoader
from c7n.utils import type_schema


class Missing(Filter):
    """Assert the absence of a particular resource.

    Intended for use at a logical account/subscription/project level

    This works as an effectively an embedded policy thats evaluated.

    :example:

    Notify if an s3 bucket is missing

    .. code-block:: yaml

            policies:
              - name: missing-s3-bucket
                resource: account
                filters:
                  - type: missing
                    policy:
                      resource: s3
                      filters:
                        - Name: my-bucket
                actions:
                  - notify
    """
    schema = type_schema(
        'missing',
        policy={'type': 'object',
                'required': ['resource'],
                'properties': {'resource': {'type': 'string'}}},
        required=['policy'])

    def __init__(self, data, manager):
        super(Missing, self).__init__(data, manager)
        self.data['policy']['name'] = self.manager.ctx.policy.name

    def validate(self):
        if 'mode' in self.data['policy']:
            raise PolicyValidationError(
                "Execution mode can't be specified in "
                "embedded policy %s" % self.data)
        if 'actions' in self.data['policy']:
            raise PolicyValidationError(
                "Actions can't be specified in "
                "embedded policy %s" % self.data)
        collection = PolicyLoader(
            self.manager.config).load_data(
                {'policies': [self.data['policy']]}, "memory://",
                session_factory=self.manager.session_factory)
        if not collection:
            raise PolicyValidationError(
                "policy %s missing filter empty embedded policy" % (
                    self.manager.ctx.policy.name))
        self.embedded_policy = list(collection).pop()
        self.embedded_policy.validate()
        return self

    def get_permissions(self):
        return self.embedded_policy.get_permissions()

    def process(self, resources, event=None):
        if not self.embedded_policy.is_runnable():
            return []

        if self.embedded_policy.poll():
            return []
        return resources
