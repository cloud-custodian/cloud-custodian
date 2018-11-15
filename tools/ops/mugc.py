# Copyright 2016-2018 Capital One Services, LLC
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
import itertools
import json
import os
import logging
import sys

from c7n.credentials import SessionFactory
from c7n.config import Config
from c7n.policy import load as policy_load
from c7n import mu

from botocore.exceptions import ClientError


log = logging.getLogger('resources')


def load_policies(options, config):
    policies = []
    for f in options.config_files:
        collection = policy_load(config, f)
        policies.extend(collection.filter(options.policy_filter))
    return policies


def region_gc(options, region, policy_config, policies):

    session_factory = SessionFactory(
        region=region,
        assume_role=policy_config.assume_role,
        profile=policy_config.profile,
        external_id=policy_config.external_id)

    manager = mu.LambdaManager(session_factory)
    funcs = list(manager.list_functions(options.prefix))
    client = session_factory().client('lambda')

    remove = []
    current_policies = [p.name for p in policies]
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
                elif principal == {'Service': 'config.amazonaws.com'}:
                    events.append(
                        mu.ConfigRule({}, session_factory))

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


def resources_gc_prefix(options, policy_config, policy_collection):
    """Garbage collect old custodian policies based on prefix.

    We attempt to introspect to find the event sources for a policy
    but without the old configuration this is implicit.
    """

    # Classify policies by region
    policy_regions = {}
    for p in policy_collection:
        if p.execution_mode == 'poll':
            continue
        policy_regions.setdefault(p.options.region, []).append(p)

    for region, policies in policy_regions:
        region_gc(options, region, policies)


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("configs", nargs='*', help="Policy configuration file(s)")
    parser.add_argument(
        '-c', '--config', dest="config_files", nargs="*", action='append',
        help="Policy configuration files(s)")
    parser.add_argument(
        '-r', '--region', action='append', dest='regions', metavar='REGION',
        help="AWS Region to target. Can be used multiple times, also supports `all`",
        default=[os.environ.get(
            'AWS_DEFAULT_REGION', 'us-east-1')])
    parser.add_argument('--dryrun', action="store_true", default=False)
    parser.add_argument(
        "--profile", default=os.environ.get('AWS_PROFILE'),
        help="AWS Account Config File Profile to utilize")
    parser.add_argument(
        "--prefix", default="custodian-",
        help="AWS Account Config File Profile to utilize")
    parser.add_argument("-p", "--policies", default=None, dest='policy_filter',
                        help="Only use named/matched policies")
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

    log_level = logging.INFO
    if options.verbose:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('c7n.cache').setLevel(logging.WARNING)

    files = []
    files.extend(itertools.chain(*options.config_files))
    files.extend(options.configs)
    options.config_files = files

    if not files:
        parser.print_help()
        sys.exit(1)

    policy_config = Config.empty(
        regions=options.regions,
        profile=options.profile,
        assume_role=options.assume_role)

    import pdb; pdb.set_trace()
    policies = load_policies(options, policy_config)
    resources_gc_prefix(options, policy_config, policies)


if __name__ == '__main__':
    main()
