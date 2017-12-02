# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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

- IAM Policy Evaluation - http://goo.gl/sH5Dt5
- IAM Policy Reference - http://goo.gl/U0a06y

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import fnmatch
import json

import six

from c7n.filters import Filter
from c7n.resolver import ValuesFrom
from c7n.utils import type_schema


def _account(arn):
    # we could try except but some minor runtime cost, basically flag
    # invalids values
    if ':' not in arn:
        return arn
    return arn.split(':', 5)[4]


class PolicyChecker(object):
    """
    checker_config:
      - check_actions: only check one of the specified actions
      - everyone_only: only check for wildcard permission grants
      - allowed_accounts: permission grants to these accounts are okay
      - whitelist_conditions: a list of conditions that are considered
            sufficient enough to whitelist the statement.
    """
    def __init__(self, checker_config):
        self.checker_config = checker_config

    # Config properties
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
        return self.checker_config.get('whitelist_conditions', ())

    @property
    def allowed_vpce(self):
        return self.checker_config.get('allowed_vpce', ())

    @property
    def allowed_vpc(self):
        return self.checker_config.get('allowed_vpc', ())

    # Policy statement handling
    def check(self, policy_text):
        if isinstance(policy_text, six.string_types):
            policy = json.loads(policy_text)
        else:
            policy = policy_text

        violations = []
        for s in policy.get('Statement', ()):
            if self.handle_statement(s):
                violations.append(s)
        return violations

    def handle_statement(self, s):
        if (all((self.handle_principal(s),
                 self.handle_effect(s),
                 self.handle_action(s))) and not self.handle_condition(s)):
            return s

    def handle_action(self, s):
        if self.check_actions:
            actions = s.get('Action')
            actions = isinstance(actions, six.string_types) and (actions,) or actions
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
        if 'Principal' not in s:
            return True
        # Skip service principals
        if 'Service' in s['Principal']:
            s['Principal'].pop('Service')
            if not s['Principal']:
                return False

        if isinstance(s['Principal'], six.string_types):
            p = s['Principal']
        else:
            p = s['Principal']['AWS']

        principal_ok = True
        p = isinstance(p, six.string_types) and (p,) or p
        for pid in p:
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

    def handle_condition(self, s):
        op, key, value = self.normalize_condition(s)
        if not op:
            return False
        if key in self.whitelist_conditions:
            return True
        handler_name = "handle_%s" % key.replace('-', '_').replace(':', '_')
        handler = getattr(self, handler_name, None)
        if handler is None:
            print("no handler:%s op:%s key:%s value:%s" % (
                handler_name, op, key, value))
            return
        return not handler(s, op, key, value)

    def normalize_condition(self, s):
        if 'Condition' not in s:
            return None, None, None

        conditions = (
            'StringEquals',
            'StringEqualsIgnoreCase',
            'StringLike',
            'ArnEquals',
            'ArnLike',
            'IpAddress',
            'NotIpAddress')
        set_conditions = ('ForAllValues', 'ForAnyValues')

        assert len(s.get('Condition').keys()) == 1, "Multiple conditions present in iam statement"
        s_cond_op = list(s['Condition'].keys())[0]

        if s_cond_op not in conditions:
            for s in set_conditions:
                if not s_cond_op.startswith(s_cond_op):
                    return None, None, None

        assert len(s['Condition'][s_cond_op]) == 1, "Multiple keys on condition"
        s_cond_key = list(s['Condition'][s_cond_op].keys())[0]

        s_cond_value = s['Condition'][s_cond_op][s_cond_key]
        s_cond_value = (
            isinstance(s_cond_value, six.string_types) and (s_cond_value,) or s_cond_value)

        return s_cond_op, s_cond_key.lower(), s_cond_value

    # Condition handlers

    # kms specific
    def handle_kms_calleraccount(self, s, op, key, values):
        return bool(set(map(_account, values)).difference(self.allowed_accounts))

    # sns default policy
    def handle_aws_sourceowner(self, s, op, key, values):
        return bool(set(map(_account, values)).difference(self.allowed_accounts))

    # s3 logging
    def handle_aws_sourcearn(self, s, op, key, values):
        return bool(set(map(_account, values)).difference(self.allowed_accounts))

    def handle_aws_sourceip(self, s, op, key, values):
        return False

    def handle_aws_sourcevpce(self, s, op, key, values):
        if not self.allowed_vpce:
            return False
        return bool(set(map(_account, values)).difference(self.allowed_vpce))

    def handle_aws_sourcevpc(self, s, op, key, values):
        if not self.allowed_vpc:
            return False
        return bool(set(map(_account, values)).difference(self.allowed_vpc))


class CrossAccountAccessFilter(Filter):
    """Check a resource's embedded iam policy for cross account access.
    """

    schema = type_schema(
        'cross-account',
        # only consider policies that grant one of the given actions.
        actions={'type': 'array', 'items': {'type': 'string'}},
        # only consider policies which grant to *
        everyone_only={'type': 'boolean'},
        # disregard statements using these conditions.
        whitelist_conditions={'type': 'array', 'items': {'type': 'string'}},
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}},
        whitelist_vpce_from=ValuesFrom.schema,
        whitelist_vpce={'type': 'array', 'items': {'type': 'string'}},
        whitepist_vpc_from=ValuesFrom.schema,
        whitelist_vpc={'type': 'array', 'items': {'type': 'string'}})

    policy_attribute = 'Policy'
    annotation_key = 'CrossAccountViolations'

    checker_factory = PolicyChecker

    def process(self, resources, event=None):
        self.everyone_only = self.data.get('everyone_only', False)
        self.conditions = set(self.data.get(
            'whitelist_conditions',
            ("aws:userid", "aws:username")))
        self.actions = self.data.get('actions', ())
        self.accounts = self.get_accounts()
        self.vpcs = self.get_vpcs()
        self.vpces = self.get_vpces()
        self.checker = self.checker_factory(
            {'allowed_accounts': self.accounts,
             'allowed_vpc': self.vpcs,
             'allowed_vpce': self.vpces,
             'check_actions': self.actions,
             'everyone_only': self.everyone_only,
             'whitelist_conditions': self.conditions})
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

    def get_resource_policy(self, r):
        return r.get(self.policy_attribute, None)

    def __call__(self, r):
        p = self.get_resource_policy(r)
        if p is None:
            return False
        violations = self.checker.check(p)
        if violations:
            r[self.annotation_key] = violations
            return True
