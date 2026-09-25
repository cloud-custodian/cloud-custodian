# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
