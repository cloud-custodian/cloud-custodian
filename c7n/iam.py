"""
IAM Resource Policy Checker
---------------------------

When securing resources with iam policies, we want to parse and evaluate
the resource's policy for any cross account or public access grants that
are not intended.

In general, iam policies can be complex, and where possible using iam simulate
is preferrable, but require passing the caller's arn, which is not feasible
when we're evaluating who the valid set of callers are.


References

- IAM Policy Evaluation - http://goo.gl/sH5Dt5
- IAM Policy Reference - http://goo.gl/U0a06y

"""
import json


def _account(arn):
    return arn.split(':', 5)[4]


def check_cross_account(policy_text, allowed_accounts):
    """Find cross account access policy grant not explicitly allowed
    """
    if isinstance(policy_text, basestring):
        p = json.loads(policy_text)
    else:
        p = policy_text

    violations = []
    for s in p['Statement']:

        principal_ok = False

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

        if p == '*':
            principal_ok = False
        else:
            account_id = _account(p)
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
