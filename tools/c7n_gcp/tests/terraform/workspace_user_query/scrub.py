#!/usr/bin/env python
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Scrub a recorded users.list response for committing as flight data.

See workspace-setup.md, next to this script, for when to run it.

Every field is classified below. Anything unclassified is an error rather
than a pass through, so that a field added by google later can't carry
personal data into the repo unnoticed. That's not hypothetical: a real phone
number reached a commit because hand scrubbing only looked for the fields we
happened to think of.
"""

import json
import pathlib
import sys

# parents[2] is tests/, from tests/terraform/workspace_user_query/
FLIGHT = (pathlib.Path(__file__).parents[2] / 'data' / 'flights'
          / 'workspace-user-query' / 'get-admin-directory-v1-users_1.json')

DOMAIN = 'example.com'
CUSTOMER_ID = 'C03abc123'

# Identifying, so rewritten deterministically from the local part.
REWRITTEN = {'id', 'etag', 'primaryEmail', 'name', 'emails',
             'nonEditableAliases', 'customerId'}

# Could carry personal data and no test needs them.
DROPPED = {'phones', 'recoveryEmail', 'recoveryPhone', 'addresses',
           'externalIds', 'relations', 'websites', 'thumbnailPhotoUrl',
           'thumbnailPhotoEtag', 'aliases', 'ims', 'organizations',
           'locations', 'keywords', 'gender', 'sshPublicKeys', 'posixAccounts',
           'customSchemas', 'notes'}

# Not identifying, and tests assert on several of them.
KEPT = {'kind', 'isAdmin', 'isDelegatedAdmin', 'isEnrolledIn2Sv',
        'isEnforcedIn2Sv', 'suspended', 'suspensionReason', 'suspensionTime',
        'archived', 'orgUnitPath', 'agreedToTerms', 'changePasswordAtNextLogin',
        'includeInGlobalAddressList', 'ipWhitelisted', 'isMailboxSetup',
        'isGuestUser', 'creationTime', 'lastLoginTime', 'deletionTime',
        'languages', 'thumbnailPhotoUrl', 'isEnrolledInAdvancedProtection'}


def local_part(email: str) -> str:
    """Test users keep their names; the super admin is anonymized.

    The super admin is whoever recorded this, so its local part is personal.
    The test_* accounts are already test names, and the state test keys off
    them.
    """
    local = email.split('@')[0]
    return local if local.startswith('test_') else 'superadmin'


def scrub_user(user: dict, index: int) -> dict:
    unknown = set(user) - REWRITTEN - DROPPED - KEPT
    if unknown:
        sys.exit(
            "unclassified field(s) %s on %s.\nAdd them to REWRITTEN, DROPPED "
            "or KEPT in %s, deciding for each whether it can identify "
            "anyone." % (sorted(unknown), user.get('primaryEmail'),
                         pathlib.Path(__file__).name))

    local = local_part(user['primaryEmail'])
    email = '%s@%s' % (local, DOMAIN)
    scrubbed = {k: v for k, v in user.items() if k in KEPT}
    scrubbed.update({
        'id': '10000000000000000000%d' % index,
        'etag': '"c7n-test-user-%d-etag"' % index,
        'primaryEmail': email,
        'name': {'givenName': local, 'familyName': 'Test',
                 'fullName': '%s Test' % local},
        'emails': [{'address': email, 'primary': True}],
        'nonEditableAliases': ['%s.test-google-a.com' % email],
        'customerId': CUSTOMER_ID,
    })
    return scrubbed


def check_scrubbable(users: list) -> None:
    """Refuse input that would be mangled rather than scrubbed."""
    if any(u['primaryEmail'].endswith('@' + DOMAIN) for u in users):
        sys.exit(
            "%s looks scrubbed already. Re-record before scrubbing: running\n"
            "this twice would anonymize the test users into one identity."
            % FLIGHT.name)

    # Only the recorder's own account is anonymized. More than one
    # non-test_ user means they'd all collapse to the same name.
    anonymized = [u['primaryEmail'] for u in users
                  if not u['primaryEmail'].split('@')[0].startswith('test_')]
    if len(anonymized) > 1:
        sys.exit(
            "expected at most one non-test_ user (the super admin), got %s.\n"
            "Name test accounts test_* so they survive scrubbing distinctly."
            % sorted(anonymized))


def main() -> int:
    doc = json.loads(FLIGHT.read_text())
    check_scrubbable(doc['body']['users'])
    doc['headers']['etag'] = '"c7n-test-users-etag"'
    doc['headers']['content-location'] = (
        'https://admin.googleapis.com/admin/directory/v1/users'
        '?customer=my_customer&alt=json')
    doc['body']['etag'] = '"c7n-test-users-etag"'
    doc['body']['users'] = [
        scrub_user(u, i)
        for i, u in enumerate(doc['body']['users'], 1)]

    FLIGHT.write_text(json.dumps(doc, indent=2) + '\n')

    print('scrubbed %d users in %s\n' % (len(doc['body']['users']), FLIGHT))
    for u in doc['body']['users']:
        print('  %-32s enrolled=%-5s enforced=%-5s suspended=%-5s %s' % (
            u['primaryEmail'], u['isEnrolledIn2Sv'], u['isEnforcedIn2Sv'],
            u['suspended'], u['orgUnitPath']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
