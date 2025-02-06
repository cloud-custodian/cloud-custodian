# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from .core import Filter
from c7n.utils import type_schema, format_string_values


class HasStatementFilter(Filter):
    """Find resources with matching access policy statements.

    If you want to return resource statements that include the listed Action or
    NotAction, you can use PartialMatch instead of an exact match.

    :example:

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
                        PartialMatch: 'Action'
    """
    PARTIAL_MATCH_ELEMENTS = ['Action', 'NotAction']
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
                    'Condition': {'type': 'object'},
                    'PartialMatch': {
                        'anyOf': [
                            {'type': 'string', "enum": PARTIAL_MATCH_ELEMENTS},
                            {'type': 'array', 'items': [
                                {"type": "string", "enum": PARTIAL_MATCH_ELEMENTS}
                            ]}
                        ]
                    }
                },
                'required': ['Effect']
            }
        })

    def process(self, resources, event=None):
        return list(filter(None, map(self.process_resource, resources)))

    def process_resource(self, resource):
        policy_attribute = getattr(self, 'policy_attribute', 'Policy')
        p = resource.get(policy_attribute)
        if p is None:
            return None
        p = json.loads(p)

        required_ids_not_found = list(self.data.get('statement_ids', []))
        resource_statements = p.get('Statement', [])
        # compare if the resource_statement sid is in the required_ids list
        for s in list(resource_statements):
            if s.get('Sid') in required_ids_not_found:
                required_ids_not_found.remove(s['Sid'])

        # required_statements is the filter that we get from the c7n policy
        required_statements = format_string_values(
            list(self.data.get('statements', [])),
            **self.get_std_format_args(resource)
            )

        found_required_statements = self.__get_matched_statements(
            required_statements,
            resource_statements
        )

        # Both statement_ids and required_statements are found in the resource
        if (not required_ids_not_found) and \
           (required_statements == found_required_statements):
            return resource
        return None

    def action_resource_case_insensitive(self, actions):
        if isinstance(actions, str):
            actionsFormatted = [actions.lower()]
        else:
            actionsFormatted = [action.lower() for action in actions]
        return set(actionsFormatted)

    def __get_matched_statements(self, required_stmts, resource_stmts):
        matched_statements = []
        for required_statement in required_stmts:
            partial_match_elements = required_statement.pop('PartialMatch', [])

            if isinstance(partial_match_elements, str):
                # If there's only one string value, make the value a list
                partial_match_elements = [partial_match_elements]

            for resource_statement in resource_stmts:
                found = 0
                for req_key, req_value in required_statement.items():
                    if req_key in ['Action', 'NotAction']:
                        resource_statement[req_key] = \
                            self.action_resource_case_insensitive(
                                resource_statement[req_key])
                        req_value = self.action_resource_case_insensitive(
                            req_value)

                    if req_key in partial_match_elements:
                        if self.__match_partial_statement(req_key,
                                                        req_value,
                                                        resource_statement):
                            found += 1

                    elif req_key in resource_statement:
                        if (req_value == resource_statement[req_key]):
                            found += 1

                if found and found == len(required_statement):
                    matched_statements.append(required_statement)
                    break
        return matched_statements

    def __match_partial_statement(self, partial_match_key,
                                partial_match_value, resource_stmt):

        # TO-DO: Add support for Condition json subset match.
        if partial_match_key in resource_stmt:
            if isinstance(partial_match_value, list):
                return set(partial_match_value).issubset(
                    resource_stmt[partial_match_key])
            elif isinstance(partial_match_value, set):
                return partial_match_value.issubset(resource_stmt[partial_match_key])
            else:
                return partial_match_value in resource_stmt[partial_match_key]
        else:
            return False
