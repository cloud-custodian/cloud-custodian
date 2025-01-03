# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from .core import Filter
from c7n.utils import type_schema, format_string_values


class HasStatementFilter(Filter):
    """Find resources with matching access policy statements.
    :Example:

    .. code-block:: yaml

            policies:
              - name: sns-check-statement-id
                resource: sns
                filters:
                  - type: has-statement
                    statement_ids:
                      - BlockNonSSL
            policies:
              - name: sns-check-block-non-ssl
                resource: sns
                filters:
                  - type: has-statement
                    statements:
                      - Effect: Deny
                        Action: 'SNS:Publish'
                        Principal: '*'
                        Condition:
                            Bool:
                                "aws:SecureTransport": "false"
    """
    schema = type_schema(
        'has-statement',
        statement_ids={'type': 'array', 'items': {'type': 'string'}},
        statements={
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'Sid': {'type': 'string'},
                    'Effect': {'type': 'string', 'enum': ['Allow', 'Deny']},
                    'Principal': {'anyOf': [
                        {'type': 'string'},
                        {'type': 'object'}, {'type': 'array'}]},
                    'NotPrincipal': {
                        'anyOf': [{'type': 'object'}, {'type': 'array'}]},
                    'Action': {
                        'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                    'NotAction': {
                        'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                    'Resource': {
                        'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                    'NotResource': {
                        'anyOf': [{'type': 'string'}, {'type': 'array'}]},
                    'Condition': {'type': 'object'}
                },
                'required': ['Effect']
            }
        })

    def process(self, resources, event=None):
        return list(filter(None, map(self.process_resource, resources)))

    def action_resource_case_insensitive(self, actions):
        if isinstance(actions, str):
            if len(actions.split(':')) > 1:
                actionsFormatted = '{}:{}'.format(actions.split(':')[0].lower(),
                    actions.split(':')[1])
            else:
                actionsFormatted = actions
        else:
            actionsFormatted = []
            for action in actions:
                actionsFormatted.append('{}:{}'.format(action.split(':')[0].lower(),
                action.split(':')[1]))
        return set(actionsFormatted)

    def process_resource(self, resource):
        policy_attribute = getattr(self, 'policy_attribute', 'Policy')
        p = resource.get(policy_attribute)
        if p is None:
            return None
        p = json.loads(p)

        required = list(self.data.get('statement_ids', []))
        statements = p.get('Statement', [])
        for s in list(statements):
            if s.get('Sid') in required:
                required.remove(s['Sid'])

        required_statements = list(self.data.get('statements', []))

        required_statements = format_string_values(list(self.data.get('statements', [])),
                                                   **self.get_std_format_args(resource))
        found_required_statements = [
            s for s in required_statements
            if self.statement_is_present(s, statements)
        ]
        if (self.data.get('statement_ids', []) and not required) or (
            self.data.get('statements', []) and
            required_statements == found_required_statements
        ):
            return resource
        return None

    def statement_is_present(self, required_statement, statements):
        for statement in statements:
            found = 0
            for key, value in required_statement.items():
                if key in ['Action', 'NotAction']:
                    if key in statement and \
                        self.action_resource_case_insensitive(value) \
                        == self.action_resource_case_insensitive(statement[key]):
                        found += 1
                else:
                    if key in statement and value == statement[key]:
                        found += 1
            if found and found == len(required_statement):
                return True
        return False
