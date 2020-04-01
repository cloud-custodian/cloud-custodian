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

import click
from c7n_azure.session import Session
from c7n.utils import yaml_dump
from azure.mgmt.resource.subscriptions import SubscriptionClient


@click.command()
@click.option(
    '-f', '--output', type=click.File('w'),
    help="File to store the generated config (default stdout)")
def main(output):
    """
    Generate a c7n-org subscriptions config file
    """

    client = SubscriptionClient(Session().get_credentials())
    subs = [sub.serialize(True) for sub in client.subscriptions.list()]
    results = []
    for sub in subs:
        sub_info = {
            'subscription_id': sub['subscriptionId'],
            'name': sub['displayName']
        }
        results.append(sub_info)

    print(yaml_dump({'subscriptions': results}), file=output)


if __name__ == '__main__':
    main()
