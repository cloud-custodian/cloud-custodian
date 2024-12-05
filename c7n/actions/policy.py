# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import hashlib

from .core import BaseAction
from c7n import utils


class RemovePolicyBase(BaseAction):

    schema = utils.type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched', "*"]},
            {'type': 'array', 'items': {'type': 'string'}}]})

    def process_policy(self, policy, resource, matched_key):
        statements = policy.get('Statement', [])
        resource_statements = resource.get(matched_key, ())

        return remove_statements(
            self.data['statement_ids'], statements, resource_statements)


def remove_statements(match_ids, statements, matched=()):
    found = []
    for s in list(statements):
        s_found = False
        if match_ids == '*':
            s_found = True
        elif match_ids == 'matched':
            if s in matched:
                s_found = True
        elif 'Sid' in s and s['Sid'] in match_ids:
            s_found = True
        if s_found:
            found.append(s)
            statements.remove(s)
    if not found:
        return None, found
    return statements, found


def statement_id(s):
    # for statements without a sid, use a checksum for identity
    return hashlib.sha224(utils.dumps(s, indent=0).encode('utf8')).hexdigest()


class ModifyPolicyBase(BaseAction):
    """Action to modify resource IAM policy statements.

    Applies to all resources with embedded IAM Policies.

    :example:

    .. code-block:: yaml

           policies:
              - name: sns-yank-cross-account
                resource: sns
                filters:
                  - type: cross-account
                actions:
                  - type: modify-policy
                    add-statements: [{
                        "Sid": "ReplaceWithMe",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["SNS:GetTopicAttributes"],
                        "Resource": topic_arn,
                            }]
                    remove-statements: '*'
    """

    schema_alias = True
    schema = utils.type_schema(
        'modify-policy',
        **{
            'add-statements': {
                'type': 'array',
                'items': {'$ref': '#/definitions/iam-statement'},
            },
            'remove-statements': {
                'type': ['array', 'string'],
                'oneOf': [
                    {'enum': ['matched', '*']},
                    {'type': 'array', 'items': {'type': 'string'}}
                ],
            }
        }
    )

    def __init__(self, data=None, manager=None):
        if manager is not None:
            config_args = {
                'account_id': manager.config.account_id,
                'region': manager.config.region
            }
            self.data = utils.format_string_values(data, **config_args)
        else:
            self.data = utils.format_string_values(data)
        self.manager = manager

    def add_statements(self, policy_statements):
        current = {s.get('Sid', statement_id(s)): s for s in policy_statements}
        additional = {s.get('Sid', statement_id(s)): s for s in self.data.get('add-statements', [])}
        current.update(additional)
        return list(current.values()), bool(additional)

    def remove_statements(self, policy_statements, resource, matched_key):
        statement_ids = self.data.get('remove-statements', [])
        found = []
        if len(statement_ids) == 0:
            return policy_statements, found
        resource_statements = resource.get(matched_key, ())
        return remove_statements(
            statement_ids, policy_statements, resource_statements)
