import argparse
import json
import os
import logging

from c7n.credentials import SessionFactory
from c7n.policy import load as policy_load
from c7n import mu, resources

log = logging.getLogger('resources')


def load_policies(options):
    policies = []
    for f in options.config_files:
        for collection in policy_load(options, f):
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
        log.info("Removing %s" % n['FunctionName'])

    for func in remove:
        events = []
        result = client.get_policy(FunctionName=func['FunctionName'])
        if 'Policy' not in result:
            pass
        else:
            p = json.loads(result['Policy'])
            for s in p['Statement']:
                principal = s.get('Principal')
                if not isinstance(principal, dict):
                    log.info("Skipping function %s" % func['FunctionName'])
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
        log.info("Removing %s" % f)

        if options.dryrun:
            log.info("Dryrun skipping")
            continue
        manager.remove(f)


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
    return parser


def main():
    parser = setup_parser()
    options = parser.parse_args()
    options.policy_filter = None
    options.log_group = None
    options.cache_period = 0
    options.cache = None
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    resources.load_resources()

    policies = load_policies(options.config_files)
    resources_gc_prefix(options, policies)




if __name__ == '__main__':
    main()
