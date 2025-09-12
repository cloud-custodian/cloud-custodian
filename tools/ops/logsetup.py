# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Cloud Watch Log Subscription Email Relay
"""
import argparse
import itertools
import logging
import sys


from c7n.credentials import SessionFactory
from c7n.mu import LambdaManager
from c7n.ufuncs import logsub

log = logging.getLogger("custodian.logsetup")


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)

    # Log Group match
    parser.add_argument("--prefix", default=None)
    parser.add_argument("-g", "--group", action="append")
    parser.add_argument("--pattern", default="Traceback")

    # Connection stuff
    parser.add_argument("--profile")
    parser.add_argument("--assume")
    parser.add_argument("--region", default="us-east-1")

    # Delivery
    parser.add_argument("--topic", required=True)
    parser.add_argument("--subject", default="Custodian Ops Error")

    return parser


def get_groups(session_factory, options):
    session = session_factory()
    logs = session.client('logs')

    params = {}
    if options.prefix:
        params['logGroupNamePrefix'] = options.prefix

    results = logs.get_paginator('describe_log_groups').paginate(**params)
    groups = list(itertools.chain(*[rp['logGroups'] for rp in results]))

    if options.group:
        log.info("Filtering on %s for %d groups" % (
            options.group,
            len([g['logGroupName'] for g in groups])))
        groups = [g for g in groups if g['logGroupName'] in options.group]

    log.info("Subscribing to groups: %s" % (
        " \n".join([g['logGroupName'] for g in groups])))
    return groups


def main():
    parser = setup_parser()
    options = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.ERROR)

    if not options.group and not options.prefix:
        print("Error: Either group or prefix must be specified")
        sys.exit(1)

    session_factory = SessionFactory(
        options.region, options.profile, options.assume)

    groups = get_groups(session_factory, options)
    func = logsub.get_function(
        session_factory,
        "cloud-custodian-error-notify",
        role=options.role,
        sns_topic=options.topic,
        subject=options.subject,
        log_groups=groups,
        pattern=options.pattern)
    manager = LambdaManager(session_factory)

    try:
        manager.publish(func)
    except Exception:
        import traceback, pdb
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


if __name__ == '__main__':
    main()
