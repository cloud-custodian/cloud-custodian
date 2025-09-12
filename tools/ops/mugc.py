# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import argparse
import itertools
import json
import os
import re
import logging
import sys

from c7n.credentials import SessionFactory
from c7n.config import Config
from c7n.policy import load as policy_load, PolicyCollection
from c7n import mu

# TODO: mugc has alot of aws assumptions

from c7n.resources.aws import AWS
from botocore.exceptions import ClientError


log = logging.getLogger('mugc')


def load_policies(options, config):
    policies = PolicyCollection([], config)
    for f in options.config_files:
        policies += policy_load(config, f).filter(options.policy_filters)
    return policies


def region_gc(options, region, policy_config, policies):

    log.debug("Region:%s Starting garbage collection", region)
    session_factory = SessionFactory(
        region=region,
        assume_role=policy_config.assume_role,
        profile=policy_config.profile,
        external_id=policy_config.external_id)

    manager = mu.LambdaManager(session_factory)
    funcs = list(manager.list_functions(options.prefix))
    client = session_factory().client('lambda')

    remove = []
    pattern = re.compile(options.policy_regex)
    for f in funcs:
        if not pattern.match(f['FunctionName']):
            continue
        match = False
        for p in policies:
            if f['FunctionName'].endswith(p.name):
                if 'region' not in p.data or p.data['region'] == region:
                    match = True
        if options.present:
            if match:
                remove.append(f)
        elif not match:
            remove.append(f)

    schedule_pattern = re.compile('^name=(.*):group=(.*)$')
    for n in remove:
        events = []
        try:
            result = client.get_policy(FunctionName=n['FunctionName'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Is it a schedule mode policy function due to empty resource policy?
                fn = client.get_function(FunctionName=n['FunctionName'])
                if 'custodian-schedule' in fn.get('Tags', {}).keys():
                    tag_value = fn.get['Tags']['custodian-schedule']
                    tag_result = schedule_pattern.search(tag_value)
                    events.append(mu.EventBridgeScheduleSource({
                        'group-name': tag_result.group(2)
                    }, session_factory))
                else:
                    log.warning(
                        "Region:%s Lambda Function or Access Policy Statement missing: %s",
                        region, n['FunctionName'])
            else:
                log.warning(
                    "Region:%s Unexpected error: %s for function %s",
                    region, e, n['FunctionName'])

            # Continue on with next function instead of raising an exception
            # if not using an EventBridge schedule
            if len(events) == 0:
                continue
            else:
                result = {}

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

        log.info("Region:%s Removing %s", region, n['FunctionName'])
        if options.dryrun:
            log.info("Dryrun skipping removal")
            continue
        manager.remove(f)
        log.info("Region:%s Removed %s", region, n['FunctionName'])


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

    regions = get_gc_regions(options.regions, policy_config)
    for r in regions:
        region_gc(options, r, policy_config, policy_regions.get(r, []))


def get_gc_regions(regions, policy_config):
    if 'all' in regions:
        session_factory = SessionFactory(
            region='us-east-1',
            assume_role=policy_config.assume_role,
            profile=policy_config.profile,
            external_id=policy_config.external_id)

        client = session_factory().client('ec2')
        return [region['RegionName'] for region in client.describe_regions()['Regions']]
    return regions


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("configs", nargs='*', help="Policy configuration file(s)")
    parser.add_argument(
        '-c', '--config', dest="config_files", nargs="*", action='append',
        help="Policy configuration files(s)", default=[])
    parser.add_argument(
        "--present", action="store_true", default=False,
        help='Target policies present in config files for removal instead of skipping them.')
    parser.add_argument(
        '-r', '--region', action='append', dest='regions', metavar='REGION',
        help="AWS Region to target. Can be used multiple times, also supports `all`")
    parser.add_argument('--dryrun', action="store_true", default=False)
    parser.add_argument(
        "--profile", default=os.environ.get('AWS_PROFILE'),
        help="AWS Account Config File Profile to utilize")
    parser.add_argument(
        "--prefix", default="custodian-",
        help="The Lambda name prefix to use for clean-up")
    parser.add_argument(
        "--policy-regex",
        help="The policy must match the regex")
    parser.add_argument("-p", "--policies", default=[], dest='policy_filters',
                        action='append', help="Only use named/matched policies")
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
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('c7n.cache').setLevel(logging.WARNING)

    if not options.policy_regex:
        options.policy_regex = f"^{options.prefix}.*"

    if not options.regions:
        options.regions = [os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')]

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

    # use cloud provider to initialize policies to get region expansion
    policies = AWS().initialize_policies(
        PolicyCollection([
            p for p in load_policies(
                options, policy_config)
            if p.provider_name == 'aws'],
            policy_config),
        policy_config)

    resources_gc_prefix(options, policy_config, policies)


if __name__ == '__main__':
    main()
