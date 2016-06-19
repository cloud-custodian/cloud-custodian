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

from c7n.filters import Filter
from c7n.utils import get_account_id, local_session, type_schema


class CrossAccountAccessFilter(Filter):
    """Matches any resource which
    """

    schema = type_schema(
        'cross-account', whitelist={'type': 'array', 'items': 'string'})

    policy_attribute = 'Policy'

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
        return super(CrossAccountAccessFilter, self).process(resources, event)

    def get_accounts(self):
        owner_id = get_account_id(local_session(self.manager.session_factory))
        accounts = set(self.data.get('whitelist', ()))
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

        # At this point principal is required?
        p = (
            isinstance(s['Principal'], basestring) and s['Principal']
            or s['Principal']['AWS'])

        p = isinstance(p, basestring) and (p,) or p
        for pid in p:
            if pid == '*':
                principal_ok = False
            else:
                account_id = _account(pid)
                if account_id not in allowed_accounts:
                    principal_ok = False

        if principal_ok:
            continue

        if 'Condition' not in s:
            violations.append(s)
            continue

        if 'ArnEquals' in s['Condition']:
            # Other valid arn equals? / are invalids allowed?
            # duplicate block from below, inline closure func
            # would remove, but slower, else move to class eval
            principal_ok = True
            v = s['Condition']['ArnEquals']['aws:SourceArn']
            v = isinstance(v, basestring) and (v,) or v
            for arn in v:
                aid = _account(arn)
                if aid not in allowed_accounts:
                    violations.append(s)
        if 'ArnLike' in s['Condition']:
            # Other valid arn equals? / are invalids allowed?
            v = s['Condition']['ArnEquals']['aws:SourceArn']
            v = isinstance(v, basestring) and (v,) or v
            principal_ok = True
            for arn in v:
                aid = _account(arn)
                if aid not in allowed_accounts:
                    violations.append(s)
        if not principal_ok:
            violations.append(s)
    return violations
