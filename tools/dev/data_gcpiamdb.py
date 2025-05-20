# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import click
import json
import requests
from bs4 import BeautifulSoup


@click.command()
@click.option('-f', '--output', default='-', type=click.File('w'))
def main(output):
    """GCP IAM DataSet
    """
    response = requests.get(
        'https://cloud.google.com/iam/docs/custom-roles-permissions-support')
    soup = BeautifulSoup(response.text, 'html.parser')
    perms = []
    for idx, row in enumerate(soup.select_one('#table-div-id').select('tr')):
        if not idx:
            continue
        perms.append(row.td.code.text)

    json.dump({'permissions': perms}, fp=output, indent=2)


if __name__ == '__main__':
    main()
