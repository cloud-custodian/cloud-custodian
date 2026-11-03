# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Refresh the discovery documents in c7n_gcp/discovery.

To add an API, save https://<name>.googleapis.com/$discovery/rest?version=<version>
there as <name>.<version>.json, then run this. Keys are sorted because the
service returns them in a different order each time.
"""
import json
from pathlib import Path

import click
import requests

DISCOVERY_DIR = Path(__file__).parent.parent / 'c7n_gcp' / 'c7n_gcp' / 'discovery'


@click.command()
def main():
    for path in sorted(DISCOVERY_DIR.glob('*.json')):
        doc = json.loads(path.read_text())
        url = f"{doc['rootUrl']}$discovery/rest?version={doc['version']}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        latest = response.json()
        path.write_text(json.dumps(latest, indent=2, sort_keys=True) + '\n')
        click.echo(f"{path.name}: revision {doc['revision']} -> {latest['revision']}")


if __name__ == '__main__':
    main()
