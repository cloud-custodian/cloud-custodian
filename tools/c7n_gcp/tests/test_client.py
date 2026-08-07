# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

import pytest

from c7n_gcp.client import (
    Session,
    get_workspace_customer,
    get_workspace_subject,
)

WORKSPACE_SCOPE = 'https://www.googleapis.com/auth/admin.directory.user.readonly'


class StubServiceAccountCredentials:
    """Minimal stand-in for google service_account.Credentials.

    Only implements the delegation surface the session uses. Notably it is
    not a google.auth Scoped instance, so with_scopes_if_required leaves it
    alone in Session.__init__.
    """

    def __init__(self, scopes=None, subject=None):
        self.scopes = scopes
        self.subject = subject

    def with_scopes(self, scopes):
        return StubServiceAccountCredentials(scopes=scopes, subject=self.subject)

    def with_subject(self, subject):
        return StubServiceAccountCredentials(scopes=self.scopes, subject=subject)


def service_account_session():
    """A session whose default credentials support delegation."""
    with mock.patch('google.auth.default',
                    return_value=(StubServiceAccountCredentials(), 'proj')):
        return Session()


def test_get_workspace_customer_defaults_to_my_customer(monkeypatch):
    monkeypatch.delenv('GOOGLE_WORKSPACE_CUSTOMER', raising=False)
    assert get_workspace_customer() == 'my_customer'


def test_get_workspace_customer_env_override(monkeypatch):
    monkeypatch.setenv('GOOGLE_WORKSPACE_CUSTOMER', 'C03abc123')
    assert get_workspace_customer() == 'C03abc123'


def test_get_workspace_subject_unset(monkeypatch):
    monkeypatch.delenv('GOOGLE_WORKSPACE_SUBJECT', raising=False)
    assert get_workspace_subject() is None


def test_unscopable_credentials_are_left_alone(monkeypatch):
    """The invariant the rest of the test suite depends on.

    Flight data replay runs on a committed authorized_user credential, which
    supports neither with_scopes nor with_subject.
    """
    monkeypatch.delenv('GOOGLE_WORKSPACE_SUBJECT', raising=False)
    session = Session()
    client = session.client(
        'admin', 'directory_v1', 'users', scopes=(WORKSPACE_SCOPE,))
    assert client._credentials is session._credentials
    assert client._use_cached_http is True


def test_declared_scopes_are_requested(monkeypatch):
    """Scopes are applied whether or not a subject is configured."""
    monkeypatch.delenv('GOOGLE_WORKSPACE_SUBJECT', raising=False)
    session = service_account_session()
    client = session.client(
        'admin', 'directory_v1', 'users', scopes=(WORKSPACE_SCOPE,))
    assert client._credentials.scopes == [WORKSPACE_SCOPE]
    assert client._credentials.subject is None


def test_subject_impersonates(monkeypatch):
    monkeypatch.setenv('GOOGLE_WORKSPACE_SUBJECT', 'admin@example.com')
    session = service_account_session()
    client = session.client(
        'admin', 'directory_v1', 'users', scopes=(WORKSPACE_SCOPE,))
    assert client._credentials.scopes == [WORKSPACE_SCOPE]
    assert client._credentials.subject == 'admin@example.com'
    # The thread cached http is authorized with the session's own
    # credentials, so a client using different credentials must not share it.
    assert client._use_cached_http is False


def test_subject_with_non_service_account_credentials_raises(monkeypatch):
    monkeypatch.setenv('GOOGLE_WORKSPACE_SUBJECT', 'admin@example.com')
    session = Session()
    with pytest.raises(ValueError) as ectx:
        session.client(
            'admin', 'directory_v1', 'users', scopes=(WORKSPACE_SCOPE,))
    assert 'GOOGLE_WORKSPACE_SUBJECT' in str(ectx.value)


def test_clients_without_scopes_are_unaffected(monkeypatch):
    monkeypatch.setenv('GOOGLE_WORKSPACE_SUBJECT', 'admin@example.com')
    session = service_account_session()
    client = session.client('compute', 'v1', 'instances')
    assert client._credentials is session._credentials
    assert client._use_cached_http is True
