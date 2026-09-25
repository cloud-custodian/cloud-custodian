# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest

import recorder
from recorder import PROJECT_NUMBER, sanitize_recording


def test_sanitize_project_number(monkeypatch):
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    assert sanitize_recording(
        '{"projectNumber": "999888777433", "entity": "project-owners-999888777433"}'
    ) == '{"projectNumber": "%s", "entity": "project-owners-%s"}' % (
        PROJECT_NUMBER, PROJECT_NUMBER)


def test_sanitize_project_number_skips_fractions(monkeypatch):
    # A learned number is scrubbed from later responses too, so a timestamp
    # fraction that happens to match it must be left alone.
    monkeypatch.setattr(recorder, 'learned_project_numbers', {'999888777433'})
    timestamp = '{"t": "2024-01-01T00:00:00.999888777433Z"}'
    assert sanitize_recording(timestamp) == timestamp


@pytest.mark.parametrize('email', [
    'service-{}@gcp-sa-pubsub.iam.gserviceaccount.com',
    'service-{}@gs-project-accounts.iam.gserviceaccount.com',
    'p{}-abc123@gcp-sa-cloud-sql.iam.gserviceaccount.com',
    '{}-compute@developer.gserviceaccount.com',
    '{}@cloudservices.gserviceaccount.com',
])
def test_sanitize_service_agent_number(monkeypatch, email):
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    # Storage ACLs name service agents as user-<email> entities.
    dirty = '{"email": "%s", "entity": "user-%s"}' % ((email.format('999888777433'),) * 2)
    assert sanitize_recording(dirty) == '{"email": "%s", "entity": "user-%s"}' % (
        (email.format(PROJECT_NUMBER),) * 2)
    assert recorder.learned_project_numbers == {'999888777433'}


def test_sanitize_ignores_user_managed_service_account(monkeypatch):
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    email = '"my-sa-999888777433@proj.iam.gserviceaccount.com"'
    sanitize_recording(email)
    assert recorder.learned_project_numbers == set()
