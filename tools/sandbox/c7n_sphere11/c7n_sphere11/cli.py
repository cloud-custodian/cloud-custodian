# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
import json
from pprint import pprint
import os

import logging
import click
import tabulate

from c7n_sphere11.client import Client

BASE_URL = os.environ.get(
    'SPHERE11_API',
    'https://5xhc1cnb7h.execute-api.us-east-1.amazonaws.com/latest/')


@click.group()
def cli():
    """Sphere11, resource locks"""
    logging.basicConfig(level=logging.INFO)


@cli.command(name='list-locks')
@click.option('--account-id', help='aws account id', required=True)
def list_locks(account_id, resource_type=None, resource_id=None):
    """Show extant locks and unlocks.
    """
    locks = Client(BASE_URL, account_id).list_locks().json()

    for r in locks:
        if 'LockDate' in r:
            r['LockDate'] = datetime.fromtimestamp(r['LockDate'])
        if 'RevisionDate' in r:
            r['RevisionDate'] = datetime.fromtimestamp(r['RevisionDate'])

    print(tabulate.tabulate(
        locks,
        headers="keys",
        tablefmt='fancy_grid'))


def validate_parent_id(ctx, param, value):
    if (ctx.params['resource_id'].startswith('sg-') and not value):
        raise click.UsageError(
            "Security Group lock status requires --parent-id flag")
    return value


@cli.command(name='lock-status')
@click.option('--account-id', help='aws account id', required=True)
@click.option('--resource-id', help='resource id', required=True)
@click.option(
    '--parent-id', help='resource parent id', callback=validate_parent_id)
def lock_status(account_id, resource_id, parent_id):
    """Show extant locks' status
    """
    return output(
        Client(BASE_URL, account_id).lock_status(resource_id, parent_id))


@cli.command()
@click.option('--resource-id', help='resource id', required=True)
@click.option('--account-id', help='aws account id', required=True)
@click.option('--region', help='aws region', required=True)
def lock(account_id, resource_id, region):
    """Lock a resource
    """
    return output(
        Client(BASE_URL, account_id).lock(resource_id, region))


@cli.command()
@click.option('--resource-id', help='resource id', required=True)
@click.option('--account-id', help='account id', required=True)
def unlock(resource_id, account_id):
    """Unlock a resource
    """
    return output(
        Client(BASE_URL, account_id).unlock(resource_id))


def output(result):
    if not result.ok:
        print("Url", result.url)
        print("Status", result.status_code)
        print("Headers")
        pprint(dict(result.headers))
        print("Body")
        print()
    try:
        print(json.dumps(result.json(), indent=2))
    except Exception:
        print(result.text)
