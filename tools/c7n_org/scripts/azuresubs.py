# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
from c7n_azure.session import Session
from c7n.utils import yaml_dump
from azure.mgmt.resource.subscriptions import SubscriptionClient

NAME_TEMPLATE = "{name}"


@click.command()
@click.option(
    '-f', '--output', type=click.File('w'),
    help="File to store the generated config (default stdout)")
@click.option(
    '-s', '--state', multiple=True, type=click.Choice(
        ['Enabled', 'Warned', 'PastDue', 'Disabled', 'Deleted']),
    default=('Enabled',),
    help="File to store the generated config (default stdout)")
@click.option(
    '--name',
    default=NAME_TEMPLATE,
    help="Name template for subscriptions in the config, defaults to %s" % NAME_TEMPLATE)
def main(output, state, name):
    """
    Generate a c7n-org subscriptions config file
    """

    client = SubscriptionClient(Session().get_credentials())
    subs = [sub.serialize(True) for sub in client.subscriptions.list()]
    results = []
    for sub in subs:
        if state and sub['state'] not in state:
            continue
        sub_info = {
            'subscription_id': sub['subscriptionId'],
            'name': sub['displayName']
        }
        sub_info['name'] = name.format(**sub_info)
        results.append(sub_info)

    print(yaml_dump({'subscriptions': results}), file=output)


if __name__ == '__main__':
    main()
