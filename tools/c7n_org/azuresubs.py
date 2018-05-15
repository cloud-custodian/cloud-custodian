# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import yaml
import click
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource.subscriptions import SubscriptionClient


@click.command()
@click.option(
    '-f', '--output', type=click.File('w'),
    help="File to store the generated config (default stdout)")
def main(output):
    """
    Generate a c7n-org subscriptions config file
    """

    tenant_auth_variables = [
        'AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET'
    ]

    # Set credentials with environment variables if all
    # required variables are present
    if not all(k in os.environ for k in tenant_auth_variables):
        raise ValueError("Missing one of the environment variables "
                         "('AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET'")
    credentials = ServicePrincipalCredentials(
        client_id=os.environ['AZURE_CLIENT_ID'],
        secret=os.environ['AZURE_CLIENT_SECRET'],
        tenant=os.environ['AZURE_TENANT_ID']
    )
    client = SubscriptionClient(credentials)
    subs = [sub.serialize(True) for sub in client.subscriptions.list()]

    results = []
    for sub in subs:
        sub_info = {
            'subscription_id': sub['subscriptionId'],
            'name': sub['displayName']
        }
        results.append(sub_info)

    print(
        yaml.safe_dump(
            {'accounts': results},
            default_flow_style=False),
        file=output)


if __name__ == '__main__':
    main()
