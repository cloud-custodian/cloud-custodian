# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# The flight data here is recorded against a real Google Workspace. To set
# that up, or to re-record, see
# terraform/workspace_user_query/workspace-setup.md

import json
import os
from unittest import mock

import pytest
from googleapiclient import discovery_cache

from c7n.config import Bag, Config
from c7n.exceptions import PolicyExecutionError
from c7n_gcp.resources.workspace import WorkspaceUser
from gcp_common import BaseTest
from terraform.workspace_user_query.workspace_sso import add_sso_assignment


class WorkspaceUserMetaTest(BaseTest):

    def get_manager(self):
        policy = Bag({'name': 'workspace-users',
                      'resource': 'gcp.workspace-user',
                      'provider_name': 'gcp'})
        ctx = self.get_context(config=Config.empty(), policy=policy)
        return WorkspaceUser(ctx, policy)

    def test_resource_query_defaults_to_my_customer(self):
        self.assertEqual(
            self.get_manager().get_resource_query(),
            {'customer': 'my_customer'})

    def test_resource_query_honors_customer_env(self):
        with mock.patch.dict(
                os.environ, {'GOOGLE_WORKSPACE_CUSTOMER': 'C03abc123'}):
            self.assertEqual(
                self.get_manager().get_resource_query(),
                {'customer': 'C03abc123'})

    def test_urn_has_no_project_or_location(self):
        self.assertEqual(
            WorkspaceUser.resource_type.get_urns(
                [{'id': '100000000000000000003',
                  'primaryEmail': 'test_no2sv@example.com'}], None),
            ['gcp:admin:::workspace-user/100000000000000000003'])

    def test_declared_scopes_accepted_by_api(self):
        """Workspace authorization is OAuth scopes plus Workspace admin
        roles, so it can't be checked against GCP IAM permissions. Validate
        the declared scopes against the API's own discovery document.
        """
        rt = WorkspaceUser.resource_type
        doc = json.loads(discovery_cache.get_static_doc(rt.service, rt.version))
        method = doc['resources'][rt.component]['methods'][rt.enum_spec[0]]
        self.assertTrue(set(rt.scopes).issubset(method['scopes']))


class WorkspaceUserQueryTest(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('workspace-user-query')
        policy = self.load_policy(
            {'name': 'workspace-users', 'resource': 'gcp.workspace-user'},
            session_factory=factory)
        resources = policy.run()
        self.assertEqual(len(resources), 5)
        # Exactly one super admin, without naming it.
        self.assertEqual(
            len([r for r in resources if r['isAdmin']]), 1)
        self.assertEqual(
            policy.resource_manager.get_urns(resources)[0],
            'gcp:admin:::workspace-user/100000000000000000001')

    def test_users_without_2sv(self):
        factory = self.replay_flight_data('workspace-user-query')
        policy = self.load_policy(
            {'name': 'workspace-users-without-mfa',
             'resource': 'gcp.workspace-user',
             'filters': [
                 {'type': 'value',
                  'key': 'isEnrolledIn2Sv',
                  'value': False}]},
            session_factory=factory)
        self.assertEqual(
            [r['primaryEmail'] for r in policy.run()],
            ['test_no2sv@example.com', 'test_no2sv_susp@example.com'])

    def test_users_without_2sv_excluding_suspended(self):
        """The policy as documented.

        Suspended users can't sign in, so a real policy excludes them. Both
        clauses matter: test_no2sv_susp differs from test_no2sv only in being
        suspended, so dropping the second clause would select it too.
        """
        factory = self.replay_flight_data('workspace-user-query')
        policy = self.load_policy(
            {'name': 'workspace-users-without-mfa',
             'resource': 'gcp.workspace-user',
             'filters': [
                 {'type': 'value',
                  'key': 'isEnrolledIn2Sv',
                  'value': False},
                 {'type': 'value',
                  'key': 'suspended',
                  'value': False}]},
            session_factory=factory)
        self.assertEqual(
            [r['primaryEmail'] for r in policy.run()],
            ['test_no2sv@example.com'])

    def test_delegated_admins_are_distinguishable(self):
        """isAdmin covers super admins only, so policies about administrators
        need isDelegatedAdmin too. Not a report field, but filterable.
        """
        factory = self.replay_flight_data('workspace-user-query')
        policy = self.load_policy(
            {'name': 'workspace-delegated-admins',
             'resource': 'gcp.workspace-user',
             'filters': [
                 {'type': 'value',
                  'key': 'isDelegatedAdmin',
                  'value': True}]},
            session_factory=factory)
        self.assertEqual(
            [r['primaryEmail'] for r in policy.run()],
            ['test_admin@example.com'])


def test_workspace_user_state(test):
    """Assert the recorded users match the table in
    terraform/workspace_user_query/workspace-setup.md

    Everything else here depends on that state, so when this fails the table
    says what to restore the workspace to before re-recording. The super
    admin is keyed by its role rather than its name, which is tenant
    specific.
    """
    expected = {
        '<super admin>':   (True, False, True, True, False, '/'),
        'test_admin':      (False, True, True, True, True, '/'),
        'test_needno2sv':  (False, False, True, False, True,
                            '/test-no-enforcement'),
        'test_no2sv':      (False, False, False, False, False,
                            '/test-no-enforcement'),
        'test_no2sv_susp': (False, False, False, True, True, '/'),
    }
    fields = ('isAdmin', 'isDelegatedAdmin', 'isEnrolledIn2Sv',
              'isEnforcedIn2Sv', 'suspended', 'orgUnitPath')

    factory = test.replay_flight_data('workspace-user-query')
    policy = test.load_policy(
        {'name': 'workspace-users', 'resource': 'gcp.workspace-user'},
        session_factory=factory)
    actual = {
        ('<super admin>' if r['isAdmin']
         else r['primaryEmail'].split('@')[0]): tuple(r[f] for f in fields)
        for r in policy.run()}
    assert actual == expected


def test_sso_assignments_are_rejected(test):
    """Resolving which assignment governs a user isn't implemented, so the
    2sv fields can't be trusted when any assignment exists.

    terraform/workspace_user_query/workspace-setup.md covers what recording
    this needs.
    """
    factory = test.replay_flight_data('workspace-user-sso-assignment')
    if test.recording:
        add_sso_assignment(test)
    policy = test.load_policy(
        {'name': 'workspace-users', 'resource': 'gcp.workspace-user'},
        session_factory=factory)
    with pytest.raises(PolicyExecutionError) as caught:
        policy.run()
    assert str(caught.value) == (
        "Organizations with SSO assignments aren't currently supported by"
        " gcp.workspace-user.")


def test_workspace_user_report_fields(test):
    factory = test.replay_flight_data('workspace-user-query')
    policy = test.load_policy(
        {'name': 'workspace-users', 'resource': 'gcp.workspace-user'},
        session_factory=factory)
    resources = policy.run()
    assert len(resources) == 5
    test.check_report_fields(policy, resources)
