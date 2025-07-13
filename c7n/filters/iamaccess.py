# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
IAM Resource Policy Checker
---------------------------

When securing resources with iam policies, we want to parse and evaluate
the resource's policy for any cross account or public access grants that
are not intended.

In general, iam policies can be complex, and where possible using iam
simulate is preferrable, but requires passing the caller's arn, which
is not feasible when we're evaluating who the valid set of callers
are.


References

- IAM Policy Evaluation
  https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html

- IAM Policy Reference
  https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html

- IAM Global Condition Context Keys
  https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html

"""
import fnmatch
import logging
import json

from c7n.filters import Filter
from c7n.resolver import ValuesFrom
from c7n.utils import type_schema

log = logging.getLogger('custodian.iamaccess')


def _account(arn):
    # we could try except but some minor runtime cost, basically flag
    # invalids values
    if arn.count(":") < 4:
        return arn
    return arn.split(':', 5)[4]


class PolicyChecker:
    """
    checker_config:
      - check_actions: only check one of the specified actions
      - everyone_only: only check for wildcard permission grants
      - return_allowed: if true, return the statements that are allowed
      - allowed_accounts: permission grants to these accounts are okay
      - whitelist_conditions: a list of conditions that are considered
            sufficient enough to whitelist the statement.
    """
    def __init__(self, checker_config):
        self.checker_config = checker_config

    # Config properties
    @property
    def return_allowed(self):
        return self.checker_config.get('return_allowed', False)

    @property
    def allowed_accounts(self):
        return self.checker_config.get('allowed_accounts', ())

    @property
    def everyone_only(self):
        return self.checker_config.get('everyone_only', False)

    @property
    def check_actions(self):
        return self.checker_config.get('check_actions', ())

    @property
    def whitelist_conditions(self):
        return set(v.lower() for v in self.checker_config.get('whitelist_conditions', ()))

    @property
    def allowed_vpce(self):
        return self.checker_config.get('allowed_vpce', ())

    @property
    def allowed_vpc(self):
        return self.checker_config.get('allowed_vpc', ())

    @property
    def allowed_orgid(self):
        return self.checker_config.get('allowed_orgid', ())

    # Policy statement handling
    def check(self, policy_text):
        if isinstance(policy_text, str):
            policy = json.loads(policy_text)
        else:
            policy = policy_text

        allowlist_statements, violations = [], []

        for s in policy.get('Statement', ()):
            if self.handle_statement(s):
                violations.append(s)
            else:
                allowlist_statements.append(s)
        return allowlist_statements if self.return_allowed else violations

    def handle_statement(self, s):
        if (all((self.handle_principal(s),
                 self.handle_effect(s),
                 self.handle_action(s))) and not self.handle_conditions(s)):
            return s

    def handle_action(self, s):
        if self.check_actions:
            actions = s.get('Action')
            actions = isinstance(actions, str) and (actions,) or actions
            for a in actions:
                if fnmatch.filter(self.check_actions, a):
                    return True
            return False
        return True

    def handle_effect(self, s):
        if s['Effect'] == 'Allow':
            return True

    def handle_principal(self, s):
        if 'NotPrincipal' in s:
            return True

        principals = s.get('Principal')
        if not principals:
            return True
        if not isinstance(principals, dict):
            principals = {'AWS': principals}

        # Ignore service principals, merge the rest into a single set
        non_service_principals = set()
        for principal_type in set(principals) - {'Service'}:
            p = principals[principal_type]
            non_service_principals.update({p} if isinstance(p, str) else p)

        if not non_service_principals:
            return False

        principal_ok = True
        for pid in non_service_principals:
            if pid == '*':
                principal_ok = False
            elif self.everyone_only:
                continue
            elif pid.startswith('arn:aws:iam::cloudfront:user'):
                continue
            else:
                account_id = _account(pid)
                if account_id not in self.allowed_accounts:
                    principal_ok = False
        return not principal_ok

    def handle_conditions(self, s):
        conditions = self.normalize_conditions(s)
        if not conditions:
            return False

        results = []
        for c in conditions:
            results.append(self.handle_condition(s, c))

        return all(results)

    def handle_condition(self, s, c):
        if not c['op']:
            return False
        if c['key'] in self.whitelist_conditions:
            return True
        handler_name = "handle_%s" % c['key'].replace('-', '_').replace(':', '_')
        handler = getattr(self, handler_name, None)
        if handler is None:
            log.warning("no handler:%s op:%s key:%s values:%s" % (
                handler_name, c['op'], c['key'], c['values']))
            return
        return not handler(s, c)

    def normalize_conditions(self, s):
        s_cond = []
        if 'Condition' not in s:
            return s_cond

        conditions = (
            'StringEquals',
            'StringEqualsIgnoreCase',
            'StringLike',
            'ArnEquals',
            'ArnLike',
            'IpAddress',
            'NotIpAddress')
        set_conditions = ('ForAllValues', 'ForAnyValues')

        for s_cond_op in list(s['Condition'].keys()):
            cond = {'op': s_cond_op}

            if s_cond_op not in conditions:
                if not any(s_cond_op.startswith(c) for c in set_conditions):
                    continue

            cond['key'] = list(s['Condition'][s_cond_op].keys())[0]
            cond['values'] = s['Condition'][s_cond_op][cond['key']]
            cond['values'] = (
                isinstance(cond['values'],
                           str) and (cond['values'],) or cond['values'])
            cond['key'] = cond['key'].lower()
            s_cond.append(cond)

        return s_cond

    # Condition handlers

    # sns default policy
    def handle_aws_sourceowner(self, s, c):
        return bool(set(map(_account, c['values'])).difference(self.allowed_accounts))

    # AWS Connect default policy on Lex
    def handle_aws_sourceaccount(self, s, c):
        return bool(set(map(_account, c['values'])).difference(self.allowed_accounts))

    # s3 logging
    def handle_aws_sourcearn(self, s, c):
        return bool(set(map(_account, c['values'])).difference(self.allowed_accounts))

    def handle_aws_sourceip(self, s, c):
        return False

    def handle_aws_sourcevpce(self, s, c):
        if not self.allowed_vpce:
            return False
        return bool(set(map(_account, c['values'])).difference(self.allowed_vpce))

    def handle_aws_sourcevpc(self, s, c):
        if not self.allowed_vpc:
            return False
        return bool(set(map(_account, c['values'])).difference(self.allowed_vpc))

    def handle_aws_principalorgid(self, s, c):
        if not self.allowed_orgid:
            return True
        return bool(set(map(_account, c['values'])).difference(self.allowed_orgid))

    def handle_aws_principalarn(self, s, c):
        """Handle the aws:PrincipalArn condition key."""

        return bool(set(map(_account, c['values'])).difference(self.allowed_accounts))

    def handle_aws_resourceorgid(self, s, c):
        """Handle the aws:resourceOrgID condition key."""

        return bool(set(map(_account, c['values'])).difference(self.allowed_orgid))

    def handle_aws_principalaccount(self, s, c):
        """Handle the aws:PrincipalAccount condition key."""
        
        return bool(set(map(_account, c['values'])).difference(self.allowed_accounts))


class CrossAccountAccessFilter(Filter):
    """Check a resource's embedded iam policy for cross account access.
    """

    schema = type_schema(
        'cross-account',
        # only consider policies that grant one of the given actions.
        actions={'type': 'array', 'items': {'type': 'string'}},
        # only consider policies which grant to *
        everyone_only={'type': 'boolean'},
        # only consider policies which grant to the specified accounts
        return_allowed={'type': 'boolean'},
        # disregard statements using these conditions.
        whitelist_conditions={'type': 'array', 'items': {'type': 'string'}},
        # white list accounts
        whitelist_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist={'type': 'array', 'items': {'type': 'string'}},
        whitelist_orgids_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_orgids={'type': 'array', 'items': {'type': 'string'}},
        whitelist_vpce_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_vpce={'type': 'array', 'items': {'type': 'string'}},
        whitelist_vpc_from={'$ref': '#/definitions/filters_common/value_from'},
        whitelist_vpc={'type': 'array', 'items': {'type': 'string'}})

    policy_attribute = 'Policy'
    annotation_key = 'CrossAccountViolations'
    allowlist_key = 'CrossAccountAllowlists'

    checker_factory = PolicyChecker

    def process(self, resources, event=None):
        self.everyone_only = self.data.get('everyone_only', False)
        self.return_allowed = self.data.get('return_allowed', False)
        self.conditions = set(self.data.get(
            'whitelist_conditions',
            ("aws:userid", "aws:username")))
        self.actions = self.data.get('actions', ())
        self.accounts = self.get_accounts()
        self.vpcs = self.get_vpcs()
        self.vpces = self.get_vpces()
        self.orgid = self.get_orgids()
        self.checker_config = getattr(self, 'checker_config', None) or {}
        self.checker_config.update(
            {'allowed_accounts': self.accounts,
             'allowed_vpc': self.vpcs,
             'allowed_vpce': self.vpces,
             'allowed_orgid': self.orgid,
             'check_actions': self.actions,
             'everyone_only': self.everyone_only,
             'whitelist_conditions': self.conditions,
             'return_allowed': self.return_allowed})
        self.checker = self.checker_factory(self.checker_config)
        return super(CrossAccountAccessFilter, self).process(resources, event)

    def get_accounts(self):
        owner_id = self.manager.config.account_id
        accounts = set(self.data.get('whitelist', ()))
        if 'whitelist_from' in self.data:
            values = ValuesFrom(self.data['whitelist_from'], self.manager)
            accounts = accounts.union(values.get_values())
        accounts.add(owner_id)
        return accounts

    def get_vpcs(self):
        vpc = set(self.data.get('whitelist_vpc', ()))
        if 'whitelist_vpc_from' in self.data:
            values = ValuesFrom(self.data['whitelist_vpc_from'], self.manager)
            vpc = vpc.union(values.get_values())
        return vpc

    def get_vpces(self):
        vpce = set(self.data.get('whitelist_vpce', ()))
        if 'whitelist_vpce_from' in self.data:
            values = ValuesFrom(self.data['whitelist_vpce_from'], self.manager)
            vpce = vpce.union(values.get_values())
        return vpce

    def get_orgids(self):
        org_ids = set(self.data.get('whitelist_orgids', ()))
        if 'whitelist_orgids_from' in self.data:
            values = ValuesFrom(self.data['whitelist_orgids_from'], self.manager)
            org_ids = org_ids.union(values.get_values())
        return org_ids

    def get_resource_policy(self, r):
        return r.get(self.policy_attribute, None)

    def __call__(self, r):
        p = self.get_resource_policy(r)
        if p is None:
            return False
        results = self.checker.check(p)
        if self.return_allowed and results:
            r[self.allowlist_key] = results
            return True

        if not self.return_allowed and results:
            r[self.annotation_key] = results
            return True
