"""Checks on the recorded responses in tests/data/placebo."""

import pathlib

PLACEBO = pathlib.Path(__file__).parent / 'data' / 'placebo'

# Placebo records every response of every client a recording session
# creates, including the sign-in that authenticated the session. These keys
# name credentials that outlive a recording and that no test replays.
# Short-lived STS session credentials are left alone: tests such as
# test_credential_sts replay AssumeRole responses on purpose.
CREDENTIAL_KEYS: tuple[str, ...] = ('accessToken', 'refreshToken', 'clientSecret')


def test_no_credentials_recorded() -> None:
    found: list[str] = []
    for path in PLACEBO.rglob('*.json'):
        text = path.read_text()
        found.extend(
            f"{path.relative_to(PLACEBO)}: {key}"
            for key in CREDENTIAL_KEYS
            if f'"{key}"' in text
            )

    assert not found, (
        "credentials recorded in placebo data; delete the file and revoke"
        " what it names: " + ', '.join(found))
