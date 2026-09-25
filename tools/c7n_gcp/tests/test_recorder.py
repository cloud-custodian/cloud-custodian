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


@pytest.mark.parametrize('dirty', [
    '{"projectNumber": "12", "a": 12, "b": "a12b"}',
    '{"project_number": 999888777433, "a": 999888777433}',
], ids=['short', 'unquoted'])
def test_sanitize_ignores_non_project_number_field(monkeypatch, dirty):
    # Every occurrence of a learned number is scrubbed, so a value that
    # isn't a real project number mustn't be learned.
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    assert sanitize_recording(dirty) == dirty


SERVICE_AGENT_EMAILS = [
    'service-{}@gcp-sa-pubsub.iam.gserviceaccount.com',
    'service-{}@gs-project-accounts.iam.gserviceaccount.com',
    'p{}-abc123@gcp-sa-cloud-sql.iam.gserviceaccount.com',
    '{}-compute@developer.gserviceaccount.com',
    '{}@cloudservices.gserviceaccount.com',
]


# Each form is sanitized on its own, since a number learned from one would
# scrub the others and hide a miss. Storage ACLs name service agents as
# user-<email> entities.
@pytest.mark.parametrize('template', ['"{}"', '"user-{}"'], ids=['email', 'acl-entity'])
@pytest.mark.parametrize('email', SERVICE_AGENT_EMAILS)
def test_sanitize_service_agent_number(monkeypatch, email, template):
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    dirty = template.format(email.format('999888777433'))
    assert sanitize_recording(dirty) == template.format(email.format(PROJECT_NUMBER))


def test_sanitize_ignores_user_managed_service_account(monkeypatch):
    monkeypatch.setattr(recorder, 'learned_project_numbers', set())
    email = '"my-sa-999888777433@proj.iam.gserviceaccount.com"'
    sanitize_recording(email)
    assert recorder.learned_project_numbers == set()
