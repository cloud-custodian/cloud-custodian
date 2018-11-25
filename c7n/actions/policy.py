
from .core import BaseAction
from c7n import utils


class RemovePolicyBase(BaseAction):

    schema = utils.type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
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
        elif s['Sid'] in match_ids:
            s_found = True
        if s_found:
            found.append(s)
            statements.remove(s)
    if not found:
        return None, found
    return statements, found


class ModifyPolicyBase(BaseAction):

    schema_alias = True
    schema = utils.type_schema(
        'modify-policy',
        **{
            'add-statements': {
                'type': 'array',
                'required': True,
                'items': {'$ref': '#/definitions/iam-statement'},
                'additionalProperties': False
            },
            'remove-statements': {
                'type': ['array', 'string'],
                'oneOf': [
                    {'enum': ['matched', '*']},
                    {'type': 'array', 'items': {'type': 'string'}}
                ],
                'required': True,
                'additionalProperties': False
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
        current = {s['Sid']: s for s in policy_statements}
        additional = {s['Sid']: s for s in self.data.get('add-statements', [])}
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
