# Copyright 2016 Capital One Services, LLC
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
import json
import logging

from c7n.filters import Filter
from c7n.resolver import ValuesFrom
from c7n.utils import get_account_id, local_session, type_schema


class CrossAccountAccessFilter(Filter):
    """Matches any resource which
    """

    schema = type_schema(
        'cross-account',
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    policy_attribute = 'Policy'

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
        return super(CrossAccountAccessFilter, self).process(resources, event)

    def get_accounts(self):
        owner_id = get_account_id(local_session(self.manager.session_factory))
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
        violations = check_cross_account(p, self.accounts)
        if violations:
            r['CrossAccountViolations'] = violations
            return True


def _account(arn):
    # we could try except but some minor runtime cost, basically flag
    # invalids values
    if ':' not in arn:
        return arn
    return arn.split(':', 5)[4]


def check_cross_account(policy_text, allowed_accounts):
    """Find cross account access policy grant not explicitly allowed
    """
    if isinstance(policy_text, basestring):
        policy = json.loads(policy_text)
    else:
        policy = policy_text

    violations = []
    for s in policy['Statement']:

        principal_ok = True

        if s['Effect'] != 'Allow':
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
        p = (
            isinstance(s['Principal'], basestring) and s['Principal']
            or s['Principal']['AWS'])

        p = isinstance(p, basestring) and (p,) or p
        for pid in p:
            if pid == '*':
                principal_ok = False
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

        ## BEGIN S3 WhiteList
        ## Note these are transient white lists for s3
        ## we need to refactor this to verify ip against a
        ## cidr white list, and verify vpce/vpc against the
        ## accounts.

            # For now allow vpce/vpc conditions as sufficient on s3
            if s['Condition']['StringEquals'].keys()[0] in (
                    "aws:sourceVpce", "aws:sourceVpce"):
                principal_ok = True

        if 'StringLike' in s['Condition']:
            # For now allow vpce/vpc conditions as sufficient on s3
            if s['Condition'][
                    'StringLike'].keys()[0].lower() == "aws:sourcevpce":
                principal_ok = True

        if 'ForAnyValue:StringLike' in s['Condition']:
            if s['Condition']['ForAnyValue:StringLike'].keys()[
                    0].lower() == 'aws:sourcevpce':
                principal_ok = True

        if 'IpAddress' in s['Condition']:
            principal_ok = True

        ## END S3 WhiteList

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
                v = isinstance(v, basestring) and (v,) or v
                for arn in v:
                    aid = _account(arn)
                    if aid not in allowed_accounts:
                        violations.append(s)
        if 'ArnLike' in s['Condition']:
            # Other valid arn equals? / are invalids allowed?
            v = s['Condition']['ArnLike']['aws:SourceArn']
            v = isinstance(v, basestring) and (v,) or v
            principal_ok = True
            for arn in v:
                aid = _account(arn)
                if aid not in allowed_accounts:
                    violations.append(s)
        if not principal_ok:
            violations.append(s)
    return violations
