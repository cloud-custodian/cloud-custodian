# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
import requests
import json

from collections import defaultdict

URL = "https://awspolicygen.s3.amazonaws.com/js/policies.js"


@click.command()
@click.option('-f', '--output', default='-', type=click.File('w'))
def main(output):
    raw_data = requests.get(URL).text
    data = json.loads(raw_data[raw_data.find('=') + 1:])

    perms = defaultdict(list)
    for _, svc in data['serviceMap'].items():
        perms[svc['StringPrefix']].extend(svc['Actions'])

    sorted_perms = {}
    for k in sorted(perms):
        sorted_perms[k] = sorted(set(perms[k]))

    json.dump(sorted_perms, fp=output, indent=2)


if __name__ == '__main__':
    main()
