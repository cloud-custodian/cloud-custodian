# Setting up to record against a Google Workspace.

This is the one-time setup needed to record the flight data for
`test_workspace.py`. For how the GCP project, Workspace account, service
account and impersonated user fit together, see
`docs/source/gcp/examples/workspace-user-mfa.rst`.

1. Obtain a domain

2. Create a workspace against that domain.
   1. See https://docs.cloud.google.com/identity/docs/how-to/set-up-cloud-identity-admin#sign-up-free
   2. Assuming you aren't a workspace customer, you'll visit
      https://workspace.google.com/gcpidentity/signup?sku=identitybasic
      That will walk you through creating a workspace admin and
      verifying you own the domain by helping you create a TXT record
      that it will read.

      Setting up users, including the admin user, will define email
      addresses. This doesn't make them deliverable.  This process
      won't mess with the domains MX records by default.

3. Do the setup that running these policies needs anyway: the service
   account, its key, the APIs, and the domain-wide delegation entry. See
   "Setup needed to use these resources" in
   `docs/source/gcp/examples/workspace-user-mfa.rst`.

   Recording needs two further scopes on that same delegation entry. No
   policy uses them; they are for `workspace_sso.py`, which gives the
   workspace an SSO assignment to record and then removes it:

   | scope | needed for |
   |-------|------------|
   | `admin.directory.orgunit.readonly` | finding the org unit to assign |
   | `cloud-identity.inboundsso` | creating and deleting the assignment |

   Delegation authorizes the exact scope requested, and a broader grant does
   not imply a narrower one: with `cloud-identity.inboundsso` granted,
   requesting `cloud-identity.inboundsso.readonly` still fails
   `unauthorized_client` until it too is listed. Scope changes take a few
   minutes to take effect.

4. Set up test users.

   This is the state the tests expect. `test_workspace_user_state` asserts
   it, so if that test fails, this table is what to restore the workspace to.

   | user              | admin | delegated admin | 2sv enrolled | 2sv enforced | suspended | org unit               |
   |-------------------|-------|-----------------|--------------|--------------|-----------|------------------------|
   | *the super admin* | yes   | no              | yes          | yes          | no        | `/`                    |
   | `test_admin`      | no    | yes             | yes          | yes          | yes       | `/`                    |
   | `test_needno2sv`  | no    | no              | yes          | no           | yes       | `/test-no-enforcement` |
   | `test_no2sv`      | no    | no              | no           | no           | no        | `/test-no-enforcement` |
   | `test_no2sv_susp` | no    | no              | no           | yes          | yes       | `/`                    |

   The documented policy in
   `docs/source/gcp/examples/workspace-user-mfa.rst` filters on
   `isEnrolledIn2Sv: false` *and* `suspended: false`, so:

   - `test_no2sv` is the only user it selects, so it is the finding.
   - `test_no2sv_susp` differs from it in only the suspended field, so the
     `suspended: false` clause is load bearing. Without that row, a one
     clause policy would select the same users and the test would prove
     nothing about the second clause.
   - `test_admin` is a delegated admin rather than a super admin. The two
     are different, and `isAdmin` alone does not find delegated admins.
   - `test_needno2sv` is enrolled but not *enforced*, so `isEnrolledIn2Sv`
     and `isEnforcedIn2Sv` are seen to vary independently.

   Drop any one of the four and exactly one of those properties disappears,
   so all of them are needed.

   `test_no2sv` lives in `/test-no-enforcement` deliberately. With 2sv
   enforced, an unenrolled user cannot sign in at all -- and signing in is
   the only way to clear google's automatic suspension. Being outside
   enforcement is what makes it recoverable.

   `test_no2sv_susp` can stay in the root org unit, because it never needs
   to sign in. That also makes it the only unenrolled *and* enforced user,
   which is what a real violation looks like.

   Enrolling 2sv needs a phone or authenticator app per account, and can
   only be done by signing in as that user. There is no API for it, which
   is why this step is manual.

5. Create a sub-organization, `test-no-enforcement`, with 2sv not enforced,
   and move `test_needno2sv` and `test_no2sv` into it.

   This comes before enforcement, because `test_no2sv` is never going to
   enroll, and enforcement would lock it out of the sign in that step 7
   needs.

6. Turn on 2sv enforcement on the root organization unit.

   **IMPORTANT! Set up 2sv on the super admin acount first!** Enforcement
   locks out anyone not enrolled, and the super admin is the account the
   tests impersonate.

7. Get the suspended column to match the table.

   Suspend `test_no2sv_susp` yourself, from the admin console. Don't wait
   for google to do it: doing it deliberately is reproducible, and shows up
   as `suspensionReason: ADMIN`.

   `test_no2sv` has to be *un*suspended, and that's the awkward one.

   Google auto suspends freshly created accounts with
   `suspensionReason: WEB_LOGIN_REQUIRED` when you create several in a
   short period. It's a periodic sweep rather than a per account timer: our
   accounts were created up to 18 minutes apart and were all suspended
   within 11 seconds of each other, about 4.5 hours later. So spacing
   creation out by a few minutes doesn't help much. What does help is
   creating the account you need unsuspended last, on its own, and
   recording promptly.

   Once it happens, **an admin cannot clear it** -- the REACTIVATE button
   is greyed out. Only the user can, by signing in at
   https://accounts.google.com and entering a code sent to a mobile phone.
   Two surprises there:

   - It asks for a phone number rather than using the one on the account.
     That's abuse throttling, not authentication.
   - It rate limits per phone number, so the number you used to enroll 2sv
     on the other accounts will likely be refused with "This phone number
     has already been used too many times for verification". You may need
     to borrow a phone.

   This is only possible at all because step 5 put `test_no2sv` outside 2sv
   enforcement: an unenrolled user can't complete a sign in while
   enforcement applies. And it matters because if `test_no2sv` stays
   suspended, the documented policy selects nothing and the test proves
   nothing.

   The remaining users can be suspended or not; no test depends on them.
   The table records what we happened to have.

8. Assign some admin role to test_admin. It doesn't matter which
   one. Whatever is first in the list is fine. :) That makes it a
   delegated admin, which is all the tests care about.

Nothing here sets up SSO. `test_sso_assignments_are_rejected` needs the
workspace to have an inbound SSO assignment, and `workspace_sso.py` creates
one while recording and removes it afterwards, so the resting state has
none. Its identity provider is mocksaml.com, whose published metadata is
kept next to this file as `mock-saml-metadata.xml`; nothing signs in through
it, it just has to be a real enough provider for Google to accept.

An assignment needs a SAML profile, and a profile is rejected as "not
complete" until a certificate has been added to it, so all three are created
and then deleted in reverse.

## Recording

Temporarily change `replay_flight_data` to `record_flight_data` in the test
you want to record, then:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
export GOOGLE_WORKSPACE_SUBJECT=<your-super-admin@your-domain>
export GOOGLE_CLOUD_PROJECT=cloud-custodian
uv run pytest tools/c7n_gcp/tests/test_workspace.py -k <test> -s -p no:env
```

`-p no:env` matters. `pyproject.toml` has a `[tool.pytest_env]` section that
loads `test.env` from *inside* pytest, which would otherwise override the
exports above and put the committed fake credentials back. That section also
deliberately unsets `GOOGLE_WORKSPACE_SUBJECT` and
`GOOGLE_WORKSPACE_CUSTOMER`, so that replaying recorded data doesn't depend
on whatever a developer happens to have in their environment.

Then scrub the recording before committing it, with:

```bash
python tools/c7n_gcp/tests/terraform/workspace_user_query/scrub.py
```

The recorder sanitizes GCP project names only, so everything else about real
users comes through. Don't scrub by hand: we did that once and shipped a real
phone number, because we checked for the fields we thought of rather than the
fields that were there. The script replaces the domain, the super admin's
identity, ids, etags and the customer id, and drops anything that could carry
personal data. It fails if it sees a field it doesn't recognize, so a future
API addition can't slip PII through unnoticed. It scrubs the recorded SSO
assignment the same way, rewriting the ids google generated for the
assignment, org unit and profile.

The `test_*` local parts are kept as they are: they're already test names, and
`test_workspace_user_state` keys off them.

Watch for stray recordings of unrelated calls as well; delete any that the
test doesn't need. Recording always leaves at least one
`...serviceAccounts-...-allowedLocations_N.json`, from signing the
delegation JWT. Replay uses fake credentials and never asks for it, and its
name carries the real project, so delete those.

Each test's replay starts numbering responses again from `_1`, so two tests
cannot share a flight directory when they need different answers to the same
call. That's why the SSO test records into `workspace-user-sso-assignment`
while everything else uses `workspace-user-query`: one needs an assignment
listed, the others need none.

Finally, change the test back to `replay_flight_data` and confirm it passes
with no other edits.

## If you get 403s on everything

During initial setup we got 403 ("Not Authorized to access this
resource/api") on every Directory API call, including reading the subject's
own record, with all of the above configured correctly. It cleared after a
while with no configuration change on our part -- though clicking around the
admin console may have had some Heisenberg effect. IDK.

So if you hit this and the setup above checks out, wait a bit and retry
before you start rearranging things.
