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
"""A cloudwatch log subscriber that records error messages into getsentry.com

Features

- For on premise sentry installations, also supports relaying through
  sqs for final delivery.

- For extant logs supports replaying them through to sentry.

- Supports self-provisioning into lambda with minimal dependency set.

- Supports collecting errors from custodian policy lambda logs or on
  ec2 instance policy logs.

- Can be run as cli against historical logs

- Auto creates projects in sentry

Todo:

- Finish lambda provision / sqs relay

Discussion:

For realtime indexing w/ custodian this is currently setup as a
lambda per account.

 - We need one lambda in the spoke account for all lambda policies
   executing in the spoke account.

 - We need one lambda in the hub account for each spoke account
   that has instance policies executing there.


OrgMode

 - Can operate with a single lambda given a mapping of accounts
   to sentry projects

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import base64
from datetime import datetime
from functools import partial
import json
import logging
import os
import time
import uuid
import zlib

# no third-party libs needed in lambda
import boto3
from botocore.exceptions import ClientError
from botocore.vendored import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil.parser import parse as parse_date
from six.moves.urllib.parse import urlparse

from c7n.config import Bag

sqs = logs = config = None

VERSION = "0.1"

log = logging.getLogger("c7n-sentry")


def init():
    """ Lambda globals cache.
    """
    global sqs, logs, config
    if config is None:
        with open('config.json') as fh:
            config = json.load(fh)
    if sqs is None:
        sqs = boto3.client('sqs')
    if logs is None:
        logs = boto3.client('logs')


def process_log_event(event, context):
    """Lambda Entrypoint - Log Subscriber

    Format log events and relay to sentry (direct or sqs)
    """
    init()
    # Grab the actual error log payload
    serialized = event['awslogs'].pop('data')
    data = json.loads(zlib.decompress(
        base64.b64decode(serialized), 16 + zlib.MAX_WBITS))
    msg = get_sentry_message(config, data)
    if msg is None:
        return
    if config['sentry_dsn']:
        # Deliver directly to sentry
        send_sentry_message(config['sentry_dsn'], msg)
    elif config['sentry_sqs']:
        # Delivery indirectly via sqs
        sqs.send_message(
            QueueUrl=config['sentry_sqs'])


def process_sqs(event, context):
    """Lambda Entrypoint - SQS
    """
    init()


def process_log_group(config):
    """CLI - Replay / Index
    """

    from c7n.credentials import SessionFactory
    factory = SessionFactory(
        config.region, config.profile, assume_role=config.role)
    session = factory()
    client = session.client('logs')

    params = dict(logGroupName=config.log_group,
                  filterPattern='Traceback', interleaved=True)
    if config.log_streams:
        params['logStreamNames'] = config.log_streams

    if config.start:
        params['startTime'] = int(time.mktime(
            parse_date(config.start).replace(
                hour=0, minute=0, second=0, microsecond=0).timetuple()) * 1000)
    if config.end:
        params['endTime'] = int(time.mktime(
            parse_date(config.end).replace(
                hour=0, minute=0, second=0, microsecond=0).timetuple()) * 1000)

    settings = dict(account_id=config.account_id,
                    account_name=config.account_name)
    paginator = client.get_paginator('filter_log_events')

    event_count = 0
    log.debug("Querying log events with %s", params)
    for p in paginator.paginate(**params):
        # log.debug("Searched streams\n %s", ", ".join(
        #    [s['logStreamName'] for s in p['searchedLogStreams']]))
        for e in p['events']:
            event_count += 1
            msg = get_sentry_message(
                settings, {'logEvents': [e],
                           'logStream': e['logStreamName'],
                           'logGroup': config.log_group}, client)
            if msg is None:
                continue
            send_sentry_message(config.sentry_dsn, msg)

    if event_count > 0:
        log.info("Processed %s %d error events", config.account_name, event_count)


def send_sentry_message(sentry_dsn, msg):
    # reversed from raven.base along with raven docs
    parsed = urlparse(sentry_dsn)
    key, secret = parsed.netloc.split('@')[0].split(':')
    project_id = parsed.path.strip('/')
    msg['project'] = project_id
    endpoint = "%s://%s/api/%s/store/" % (
        parsed.scheme, parsed.netloc.split('@')[1], project_id)

    client = 'custodian-python-%s' % VERSION
    auth_header_keys = [
        ('sentry_timestamp', time.time()),
        ('sentry_client', client),
        ('sentry_version', '7'),  # try 7?
        ('sentry_key', key),
        ('sentry_secret', secret)]
    auth_header = "Sentry %s" % ', '.join(
        "%s=%s" % (k, v) for k, v in auth_header_keys)
    headers = {
        'User-Agent': client,
        'X-Sentry-Auth': auth_header,
        'Content-Encoding': 'deflate',
        'Content-Type': 'application/octet-stream'}
    encoded = zlib.compress(json.dumps(msg).encode('utf8'))
    result = requests.post(endpoint, data=encoded, headers=headers)
    if result.status_code != 200:
        log.info("Got status code %s" % result.status_code)


def get_sentry_message(config, data, log_client=None, is_lambda=True):
    # Policy name extraction from log group and stream.
    group = data['logGroup']
    stream = data['logStream']

    if group.startswith('/aws/lambda'):
        policy = "-".join(group.split('/')[-1].split('-')[1:])
        module_prefix = "/var/task"
    else:
        policy = stream
        module_prefix = "site-package"

    # Parse the stringified traceback to get a structured exception
    # for sentry.
    try:
        error_msg, error = parse_traceback(
            data['logEvents'][0]['message'], module_prefix)
    except IndexError:
        # error messages without a traceback .. skip
        log.info("no traceback, %s" % data['logEvents'][0]['message'])
        return None

    # WARNING - highly log format dependent :-(
    try:
        _, level, logger, msg_frag = [s.strip() for s in error_msg[
            error_msg.find(','):].split('-', 3)]
        error_msg = " - ".join([level, logger, msg_frag])
    except:
        level, logger = 'ERROR', None

    for f in reversed(error['stacktrace']['frames']):
        culprit = "%s.%s" % (f['module'], f['function'])
        if f['module'].startswith('c7n'):
            break

    breadcrumbs = None
    # Fetch additional logs for context (10s window)
#    if 0:
#        timestamps = [e['timestamp'] for e in data['logEvents']]
#        start = min(timestamps) - 1000 * 10
#        end = max(timestamps) + 1000
#        breadcrumbs = log_client.get_log_events(
#            logGroupName=data['logGroup'],
#            logStreamName=data['logStream'],
#            startTime=start,
#            endTime=end,
#            startFromHead=True)['events'][:5]
#        if data['logEvents'][0] in breadcrumbs:
#            breadcrumbs.remove(data['logEvents'][0])
#    else:

    sentry_msg = {
        'event_id': uuid.uuid4().hex,
        'timestamp': datetime.fromtimestamp(
            data['logEvents'][0]['timestamp'] / 1000).isoformat(),
        'user': {
            'id': config['account_id'],
            'username': config['account_name']},
        'level': level.lower(),
        'culprit': culprit,
        'message': error_msg,
        'platform': 'python',
        'exception': {'values': [error]},
        'tags': {
            'policy': policy,
            'stream': stream,
            'group': group},
    }

    if logger:
        sentry_msg['logger'] = logger
    if breadcrumbs:
        sentry_msg['breadcrumbs'] = [
            {'category': 'policy',
             'message': e['message'],
             'timestamp': e['timestamp'] / 1000} for e in breadcrumbs]
    return sentry_msg


def parse_traceback(msg, site_path="site-packages", in_app_prefix="c7n"):
    """Extract a sentry traceback structure,

    From a python formatted traceback string per python stdlib
    traceback.print_exc()
    """

    data = {}
    lines = list(filter(None, msg.split('\n')))
    data['frames'] = []
    err_ctx = None

    for l in lines[1:-1]:
        l = l.strip()
        if l.startswith('Traceback'):
            continue
        elif l.startswith('File'):
            abs_path, lineno, function = l.split(',', 3)
            abs_path = abs_path[abs_path.find('"'):-1]
            f_path = abs_path[abs_path.find(site_path) + len(site_path) + 1:]
            module = f_path[:f_path.find('.')].replace('/', '.').strip('.')
            lineno = int(lineno.strip().split()[1])
            function = function.strip().split()[-1]
            err_ctx = dict(lineno=lineno,
                           abs_path=abs_path,
                           function=function,
                           filename=f_path,
                           module=module)
            if module.startswith(in_app_prefix):
                err_ctx['in_app'] = True
        elif err_ctx is not None:
            err_ctx['context_line'] = l
            data['frames'].append(err_ctx)
            err_ctx = None

    return lines[0], {
        'type': lines[-1].strip().split(':')[0],
        'value': lines[-1].strip().split(':', 1)[1].strip(),
        'module': data['frames'][-1]['module'],
        'stacktrace': data}


def get_function(session_factory, name, handler, runtime, role,
                 log_groups,
                 project, account_name, account_id,
                 sentry_dsn,
                 pattern="Traceback"):
    """Lambda function provisioning.

    Self contained within the component, to allow for easier reuse.
    """
    # Lazy import to avoid runtime dependency
    from c7n.mu import (
        LambdaFunction, PythonPackageArchive, CloudWatchLogSubscription)

    config = dict(
        name=name,
        handler=handler,
        runtime=runtime,
        memory_size=512,
        timeout=15,
        role=role,
        description='Custodian Sentry Relay',
        events=[
            CloudWatchLogSubscription(
                session_factory, log_groups, pattern)])

    archive = PythonPackageArchive('c7n_sentry')
    archive.add_contents(
        'config.json', json.dumps({
            'project': project,
            'account_name': account_name,
            'account_id': account_id,
            'sentry_dsn': sentry_dsn,
        }))
    archive.add_contents(
        'handler.py',
        'from c7n_sentry.c7nsentry import process_log_event'
    )
    archive.close()

    return LambdaFunction(config, archive)


def orgreplay(options):
    from .common import get_accounts
    accounts = get_accounts(options)

    auth_headers = {'Authorization': 'Bearer %s' % options.sentry_token}

    sget = partial(requests.get, headers=auth_headers)
    spost = partial(requests.post, headers=auth_headers)

    dsn = urlparse(options.sentry_dsn)
    endpoint = "%s://%s/api/0/" % (
        dsn.scheme,
        "@" in dsn.netloc and dsn.netloc.rsplit('@', 1)[1] or dsn.netloc)

    log.info("sentry endpoint: %s", endpoint)
    teams = set([t['slug'] for t in sget(
        endpoint + "organizations/%s/teams/" % options.sentry_org).json()])
    projects = {p['name']: p for p in sget(endpoint + "projects/").json()}

    def process_account(a):
        log.debug("processing %s", a['name'])
        team_name = a['name'].rsplit('-', 1)[0]
        if team_name not in teams:

            log.info("creating org team %s", team_name)
            spost(
                endpoint + "organizations/%s/teams/" % options.sentry_org,
                json={'name': team_name})
            teams.add(team_name)

        if a['name'] not in projects:
            log.info("creating account project %s", a['name'])
            spost(endpoint + "teams/%s/%s/projects/" % (
                options.sentry_org, team_name),
                json={'name': a['name']})

        bagger = partial(
            Bag,
            profile=options.profile, role=None, log_streams=None,
            start=options.start, end=options.end, sentry_dsn=options.sentry_dsn,
            account_id=a['account_id'],
            account_name=a['name'])

        for r in options.regions:
            log.debug("Fetching hub instance policy errors for %s", a['name'])
            b = bagger(
                region=r, log_group="/cloud-custodian/%s/%s" % (a['name'], r))

            try:
                process_log_group(b)
            except ClientError as e:
                log.warning("Could not process %s region %s error: %s",
                            a['name'], r, e)
            log.debug("Fetching spoke lambda policy errors for %s", a['name'])
            for fname, config in a['config_files'].items():
                for p in config.get('policies', ()):
                    if not p.get('mode'):
                        continue
                    b = bagger(region=r, assume_role=a['role'],
                               log_group="/aws/lambda/custodian-%s" % p['name'])
                    try:
                        process_log_group(b)
                    except ClientError as e:
                        if e.response['Error']['Code']:
                            log.info("account: %s region: %s group: %s not found",
                                    a['name'], r, b.log_group)
                            continue

    return [process_account(a) for a in accounts]

    with ThreadPoolExecutor(max_workers=3) as w:
        futures = {}
        for a in accounts:
            futures[w.submit(process_account, a)] = a
        for f in as_completed(futures):
            exc = f.exception()
            if exc:
                log.error("Error processing account %s: %r", a['name'], exc)


def deploy(options):
    from .common import get_accounts
    for account in get_accounts(options):
        for region_name in options.regions:
            for fname, config in account['config_files'].items():
                for policy in config.get('policies', ()):
                    if policy.get('mode'):
                        deploy_one(
                            region_name, account, policy, options.sentry_dsn)


def deploy_one(region_name, account, policy, sentry_dsn):
    from c7n.mu import LambdaManager

    def session_factory():
        return boto3.Session(region_name=region_name)
    log_group_name = '/aws/lambda/custodian-{}'.format(policy['name'])
    arn = 'arn:aws:logs:{}:{}:log-group:{}:*'.format(
        region_name, account['account_id'], log_group_name)
    function = get_function(
        session_factory=session_factory,
        name='cloud-custodian-sentry',
        handler='handler.process_log_event',
        runtime=account.get('runtime', 'python2.7'),
        role=account['role'],
        log_groups=[{'logGroupName': log_group_name, 'arn': arn}],
        project=None,
        account_name=account['name'],
        account_id=account['account_id'],
        sentry_dsn=sentry_dsn,
    )
    log.info("Deploying lambda for {} in {}".format(
        log_group_name, region_name))
    LambdaManager(session_factory).publish(function)


def setup_parser():
    from .common import setup_parser as common_parser

    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', default=False, action="store_true")
    subs = parser.add_subparsers(dest='command')
    subs.required = True

    cmd_orgreplay = subs.add_parser('orgreplay')
    common_parser(cmd_orgreplay)
    cmd_orgreplay.set_defaults(command=orgreplay)
    cmd_orgreplay.add_argument('--profile')
    # cmd_orgreplay.add_argument('--role')
    cmd_orgreplay.add_argument('--start')
    cmd_orgreplay.add_argument('--end')
    cmd_orgreplay.add_argument('--sentry-org', default="c7n")
    cmd_orgreplay.add_argument('--sentry-dsn',
                               default=os.environ.get('SENTRY_DSN'))
    cmd_orgreplay.add_argument('--sentry-token',
                               default=os.environ.get('SENTRY_TOKEN'))

    cmd_deploy = subs.add_parser('deploy')
    common_parser(cmd_deploy)
    cmd_deploy.add_argument('--sentry-dsn',
                            default=os.environ.get('SENTRY_DSN'))
    cmd_deploy.set_defaults(command=deploy)

    return parser


def main():
    parser = setup_parser()
    options = parser.parse_args()
    level = options.verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.ERROR)

    if not options.regions:
        options.regions = ["us-east-1", "us-west-2"]
    options.command(options)


if __name__ == '__main__':

    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except:
        import traceback, sys, pdb
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
