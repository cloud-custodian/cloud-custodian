# Copyright 2016-2017 Capital One Services, LLC
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
import argparse
import json
import os
import logging

from c7n.credentials import SessionFactory
from c7n.policy import load as policy_load
from c7n import mu, resources

from botocore.exceptions import ClientError

log = logging.getLogger('resources')


def load_policies(options):
    policies = []
    for f in options.config_files:
        collection = policy_load(options, f)
        policies.extend(collection.filter(options.policy_filter))
    return policies


def resources_gc_prefix(options, policy_collection):
    """Garbage collect old custodian policies based on prefix.

    We attempt to introspect to find the event sources for a policy
    but without the old configuration this is implicit.
    """
    session_factory = SessionFactory(
        options.region, options.profile, options.assume_role)

    manager = mu.LambdaManager(session_factory)
    funcs = list(manager.list_functions('custodian-'))

    client = session_factory().client('lambda')

    remove = []
    current_policies = [p.name for p in policy_collection]
    for f in funcs:
        pn = f['FunctionName'].split('-', 1)[1]
        if pn not in current_policies:
            remove.append(f)

    for n in remove:
        events = []
        try:
            result = client.get_policy(FunctionName=n['FunctionName'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                log.warn("Lambda Function or Access Policy Statement missing: {}".
                    format(n['FunctionName']))
            else:
                log.warn("Unexpected error: {} for function {}".
                    format(e, n['FunctionName']))

            # Continue on with next function instead of raising an exception
            continue

        if 'Policy' not in result:
            pass
        else:
            p = json.loads(result['Policy'])
            for s in p['Statement']:
                principal = s.get('Principal')
                if not isinstance(principal, dict):
                    log.info("Skipping function %s" % n['FunctionName'])
                    continue
                if principal == {'Service': 'events.amazonaws.com'}:
                    events.append(
                        mu.CloudWatchEventSource({}, session_factory))

        f = mu.LambdaFunction({
            'name': n['FunctionName'],
            'role': n['Role'],
            'handler': n['Handler'],
            'timeout': n['Timeout'],
            'memory_size': n['MemorySize'],
            'description': n['Description'],
            'runtime': n['Runtime'],
            'events': events}, None)

        log.info("Removing %s" % n['FunctionName'])
        if options.dryrun:
            log.info("Dryrun skipping removal")
            continue
        manager.remove(f)
        log.info("Removed %s" % n['FunctionName'])


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--config',
        required=True, dest="config_files", action="append")
    parser.add_argument(
        '-r', '--region', default=os.environ.get(
            'AWS_DEFAULT_REGION', 'us-east-1'))
    parser.add_argument('--dryrun', action="store_true", default=False)
    parser.add_argument(
        "--profile", default=os.environ.get('AWS_PROFILE'),
        help="AWS Account Config File Profile to utilize")
    parser.add_argument(
        "--assume", default=None, dest="assume_role",
        help="Role to assume")
    parser.add_argument(
        "-v", dest="verbose", action="store_true", default=False,
        help='toggle verbose logging')
    return parser


def main():
    parser = setup_parser()
    options = parser.parse_args()
    options.policy_filter = None
    options.log_group = None
    options.external_id = None
    options.cache_period = 0
    options.cache = None
    log_level = logging.INFO
    if options.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('c7n.cache').setLevel(logging.WARNING)
    resources.load_resources()

    policies = load_policies(options)
    resources_gc_prefix(options, policies)


if __name__ == '__main__':
    main()
