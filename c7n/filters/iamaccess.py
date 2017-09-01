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
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    policy_attribute = 'Policy'
    annotation_key = 'CrossAccountViolations'

    def process(self, resources, event=None):
        self.everyone_only = self.data.get('everyone_only', False)
        self.conditions = set(self.data.get(
            'whitelist_conditions',
            ("aws:sourcevpce", "aws:sourcevpc", "aws:userid", "aws:username")))
        self.actions = self.data.get('actions', ())
        self.accounts = self.get_accounts()
        return super(CrossAccountAccessFilter, self).process(resources, event)

    def get_accounts(self):
        owner_id = self.manager.config.account_id
        accounts = set(self.data.get('whitelist', ()))
        if 'whitelist_from' in self.data:
            values = ValuesFrom(self.data['whitelist_from'], self.manager)
            accounts = accounts.union(values.get_values())
        accounts.add(owner_id)
        return accounts

    def get_resource_policy(self, r):
        return r.get(self.policy_attribute, None)

    def __call__(self, r):
        p = self.get_resource_policy(r)
        if p is None:
            return False
        violations = check_cross_account(
            p, self.accounts, self.everyone_only, self.conditions, self.actions)
        if violations:
            r[self.annotation_key] = violations
            return True


def _account(arn):
    # we could try except but some minor runtime cost, basically flag
    # invalids values
    if ':' not in arn:
        return arn
    return arn.split(':', 5)[4]


def check_cross_account(policy_text, allowed_accounts, everyone_only,
                        conditions, check_actions):
    """Find cross account access policy grant not explicitly allowed
    """
    if isinstance(policy_text, six.string_types):
        policy = json.loads(policy_text)
    else:
        policy = policy_text

    violations = []
    for s in policy['Statement']:

        principal_ok = True

        if s['Effect'] != 'Allow':
            continue

        if check_actions:
            actions = s.get('Action')
            actions = isinstance(actions, six.string_types) and (actions,) or actions
            found = False
            for a in actions:
                if fnmatch.filter(check_actions, a):
                    found = True
                    break
            if not found:
                continue

        # Highly suspect in an allow
        if 'NotPrincipal' in s:
            violations.append(s)
            continue
        # Does this wildcard
        if 'Principal' not in s:
            violations.append(s)
            continue

        # Skip relays for events to sns
        if 'Service' in s['Principal']:
            s['Principal'].pop('Service')
            if not s['Principal']:
                continue

        assert len(s['Principal']) == 1, "Too many principals %s" % s

        # At this point principal is required?
        if isinstance(s['Principal'], six.string_types):
            p = s['Principal']
        else:
            p = s['Principal']['AWS']

        p = isinstance(p, six.string_types) and (p,) or p
        for pid in p:
            if pid == '*':
                principal_ok = False
            elif everyone_only:
                continue
            elif pid.startswith('arn:aws:iam::cloudfront:user'):
                continue
            else:
                account_id = _account(pid)
                if account_id not in allowed_accounts:
                    principal_ok = False

        if principal_ok:
            continue

        if 'Condition' not in s:
            violations.append(s)
            continue

        whitelist_conditions = conditions

        if 'StringEquals' in s['Condition']:
            # Default SNS Policy does this
            if 'AWS:SourceOwner' in s['Condition']['StringEquals']:
                so = s['Condition']['StringEquals']['AWS:SourceOwner']
                if not isinstance(so, list):
                    so = [so]
                so = [pso for pso in so if pso not in allowed_accounts]
                if not so:
                    principal_ok = True

            # Default keys in kms do this
            if 'kms:CallerAccount' in s['Condition']['StringEquals']:
                so = s['Condition']['StringEquals']['kms:CallerAccount']
                if so in allowed_accounts:
                    principal_ok = True

        # BEGIN S3 WhiteList
        # Note these are transient white lists for s3
        # we need to refactor this to verify ip against a
        # cidr white list, and verify vpce/vpc against the
        # accounts.

            # For now allow vpce/vpc conditions as sufficient on s3
            if list(s['Condition']['StringEquals'].keys())[0].lower() in whitelist_conditions:
                principal_ok = True

        if 'StringLike' in s['Condition']:
            # For now allow vpce/vpc conditions as sufficient on s3
            if list(s['Condition'][
                    'StringLike'].keys())[0].lower() in whitelist_conditions:
                principal_ok = True

        if 'ForAnyValue:StringLike' in s['Condition']:
            if list(
                s['Condition'][
                    'ForAnyValue:StringLike'].keys())[0].lower() in whitelist_conditions:
                principal_ok = True

        if 'IpAddress' in s['Condition']:
            principal_ok = True

        # END S3 WhiteList

        if 'ArnEquals' in s['Condition']:
            # Other valid arn equals? / are invalids allowed?
            # duplicate block from below, inline closure func
            # would remove, but slower, else move to class eval
            principal_ok = True

            keys = ('aws:SourceArn', 'AWS:SourceArn')
            for k in keys:
                if k in s['Condition']['ArnEquals']:
                    v = s['Condition']['ArnEquals'][k]
            if v is None:
                violations.append(s)
            else:
                v = isinstance(v, six.string_types) and (v,) or v
                for arn in v:
                    aid = _account(arn)
                    if aid not in allowed_accounts:
                        violations.append(s)
        if 'ArnLike' in s['Condition']:
            # Other valid arn equals? / are invalids allowed?
            for k in ('aws:SourceArn', 'AWS:SourceArn'):
                v = s['Condition']['ArnLike'].get(k)
                if v:
                    break
            v = isinstance(v, six.string_types) and (v,) or v
            principal_ok = True
            for arn in v:
                aid = _account(arn)
                if aid not in allowed_accounts:
                    violations.append(s)
        if not principal_ok:
            violations.append(s)
    return violations
