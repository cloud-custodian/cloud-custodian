# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from botocore.exceptions import ClientError
import boto3
import click
import json
from c7n.credentials import assumed_session
from c7n.utils import get_retry, dumps, chunks
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dateutil.tz import tzutc, tzlocal
from dateutil.parser import parse
import fnmatch
import functools
import jsonschema
import logging
import sys
import time
import os
import operator
from tabulate import tabulate
import yaml

from c7n.executor import MainThreadExecutor
MainThreadExecutor.c7n_async = False

logging.basicConfig(level=logging.INFO)
logging.getLogger('c7n.worker').setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)

log = logging.getLogger('c7n-log-exporter')


CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    'id': 'http://schema.cloudcustodian.io/v0/logexporter.json',
    'definitions': {
        'subscription': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['destination-arn'],
            'properties': {
                'destination-arn': {'type': 'string'},
                'destination-role': {'type': 'string'},
                'managed-policy': {'type': 'boolean'},
                'name': {'type': 'string'},
            },
        },
        'destination': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['bucket'],
            'properties': {
                'bucket': {'type': 'string'},
                'prefix': {'type': 'string'},
            },
        },
        'account': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['role', 'groups'],
            'properties': {
                'name': {'type': 'string'},
                'role': {'oneOf': [
                    {'type': 'array', 'items': {'type': 'string'}},
                    {'type': 'string'}]},
                'groups': {
                    'type': 'array', 'items': {'type': 'string'}
                }
            }
        }
    },
    'type': 'object',
    'additionalProperties': False,
    'required': ['accounts', 'destination'],
    'properties': {
        'accounts': {
            'type': 'array',
            'items': {'$ref': '#/definitions/account'}
        },
        'destination': {'$ref': '#/definitions/destination'},
        'subscription': {'$ref': '#/definitions/subscription'}
    }
}


def debug(func):
    @functools.wraps(func)
    def run(*args, **kw):
        try:
            return func(*args, **kw)
        except SystemExit:
            raise
        except Exception:
            import traceback
            import pdb
            import sys
            traceback.print_exc()
            pdb.post_mortem(sys.exc_info()[-1])
            raise
    return run


@click.group()
def cli():
    """c7n cloudwatch log group exporter"""


@cli.command()
@click.option('--config', type=click.Path())
def validate(config):
    """validate config file"""
    with open(config) as fh:
        content = fh.read()

    try:
        data = yaml.safe_load(content)
    except Exception:
        log.error("config file: %s is not valid yaml", config)
        raise

    try:
        jsonschema.validate(data, CONFIG_SCHEMA)
    except Exception:
        log.error("config file: %s is not valid", config)
        raise

    log.info("config file valid, accounts:%d", len(data['accounts']))
    return data


def _process_subscribe_group(client, group_name, subscription, distribution):
    sub_name = subscription.get('name', 'FlowLogStream')
    filters = client.describe_subscription_filters(
        logGroupName=group_name).get('subscriptionFilters', ())
    if filters:
        f = filters.pop()
        if (f['filterName'] == sub_name and
                f['destinationArn'] == subscription['destination-arn'] and
                f['distribution'] == distribution):
            return
    client.delete_subscription_filter(
        logGroupName=group_name, filterName=sub_name)
    client.put_subscription_filter(
        logGroupName=group_name,
        destinationArn=subscription['destination-arn'],
        filterName=sub_name,
        filterPattern="",
        distribution=distribution)


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('-r', '--region', multiple=False)
@click.option('--merge', is_flag=True, default=False)
@click.option('--debug', is_flag=True, default=False)
def subscribe(config, accounts, region, merge, debug):
    """subscribe accounts log groups to target account log group destination"""
    config = validate.callback(config)
    subscription = config.get('subscription')

    if subscription is None:
        log.error("config file: logs subscription missing")
        sys.exit(1)

    def converge_destination_policy(client, config):
        destination_name = subscription['destination-arn'].rsplit(':', 1)[-1]
        try:
            extant_destinations = client.describe_destinations(
                DestinationNamePrefix=destination_name).get('destinations')
        except ClientError:
            log.error("Log group destination not found: %s",
                      subscription['destination-arn'])
            sys.exit(1)

        account_ids = set()
        for a in accounts:
            if isinstance(a['role'], list):
                account_ids.add(a['role'][-1].split(':')[4])
            else:
                account_ids.add(a['role'].split(':')[4])

        if merge:
            for d in extant_destinations:
                if d['destinationName'] == destination_name:
                    for s in json.loads(d['accessPolicy']):
                        if s['Sid'] == 'CrossAccountDelivery':
                            account_ids.update(s['Principal']['AWS'])

        client.put_destination_policy(
            destinationName=destination_name,
            accessPolicy=json.dumps({
                'Statement': [{
                    'Action': 'logs:PutSubscriptionFilter',
                    'Effect': 'Allow',
                    'Principal': {'AWS': list(account_ids)},
                    'Resource': subscription['destination-arn'],
                    'Sid': 'CrossAccountDelivery'}]}))

    def subscribe_account(t_account, subscription, region):
        session = get_session(t_account['role'], region)
        client = session.client('logs')
        distribution = subscription.get('distribution', 'ByLogStream')

        for g in account.get('groups'):
            if (g.endswith('*')):
                g = g.replace('*', '')
                paginator = client.get_paginator('describe_log_groups')
                allLogGroups = paginator.paginate(logGroupNamePrefix=g).build_full_result()
                for l in allLogGroups:
                    _process_subscribe_group(
                        client, l['logGroupName'], subscription, distribution)
            else:
                _process_subscribe_group(client, g, subscription, distribution)

    if subscription.get('managed-policy'):
        if subscription.get('destination-role'):
            session = get_session(subscription['destination-role'], region)
        else:
            session = boto3.Session()
        converge_destination_policy(session.client('logs'), config)

    executor = debug and MainThreadExecutor or ThreadPoolExecutor

    with executor(max_workers=32) as w:
        futures = {}
        for account in config.get('accounts', ()):
            if accounts and account['name'] not in accounts:
                continue
            futures[w.submit(subscribe_account, account, subscription, region)] = account

        for f in as_completed(futures):
            account = futures[f]
            if f.exception():
                log.error("Error on account %s err: %s",
                          account['name'], f.exception())
            log.info("Completed %s", account['name'])


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('--start', required=True)
@click.option('--end')
@click.option('-a', '--accounts', multiple=True)
@click.option('-r', '--region', multiple=False)
@click.option('--debug', is_flag=True, default=False)
def run(config, start, end, accounts, region, debug):
    """run export across accounts and log groups specified in config."""
    config = validate.callback(config)
    destination = config.get('destination')
    start = start and parse(start) or start
    end = end and parse(end) or datetime.now()
    executor = debug and MainThreadExecutor or ThreadPoolExecutor
    with executor(max_workers=32) as w:
        futures = {}
        for account in config.get('accounts', ()):
            if accounts and account['name'] not in accounts:
                continue
            futures[
                w.submit(process_account, account, start,
                         end, destination, region)] = account
        for f in as_completed(futures):
            account = futures[f]
            if f.exception():
                log.error("Error on account %s err: %s",
                          account['name'], f.exception())
            log.info("Completed %s", account['name'])


def lambdafan(func):
    """simple decorator that will auto fan out async style in lambda.

    outside of lambda, this will invoke synchrously.
    """
    if 'AWS_LAMBDA_FUNCTION_NAME' not in os.environ:
        return func

    @functools.wraps(func)
    def scaleout(*args, **kw):
        client = boto3.client('lambda')
        client.invoke(
            FunctionName=os.environ['AWS_LAMBDA_FUNCTION_NAME'],
            InvocationType='Event',
            Payload=dumps({
                'event': 'fanout',
                'function': func.__name__,
                'args': args,
                'kwargs': kw}),
            Qualifier=os.environ['AWS_LAMBDA_FUNCTION_VERSION'])
    return scaleout


@lambdafan
def process_account(account, start, end, destination, region, incremental=True):
    session = get_session(account['role'], region)
    client = session.client('logs')

    paginator = client.get_paginator('describe_log_groups')
    all_groups = []
    for p in paginator.paginate():
        all_groups.extend([g for g in p.get('logGroups', ())])

    group_count = len(all_groups)
    groups = filter_creation_date(
        filter_group_names(all_groups, account['groups']),
        start, end)

    if incremental:
        groups = filter_last_write(client, groups, start)

    account_id = session.client('sts').get_caller_identity()['Account']
    prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id

    log.info("account:%s matched %d groups of %d",
             account.get('name', account_id), len(groups), group_count)

    if not groups:
        log.warning("account:%s no groups matched, all groups \n  %s",
                    account.get('name', account_id), "\n  ".join(
                        [g['logGroupName'] for g in all_groups]))
    t = time.time()
    for g in groups:
        export.callback(
            g,
            destination['bucket'], prefix,
            g['exportStart'], end, account['role'],
            name=account['name'])

    log.info("account:%s exported %d log groups in time:%0.2f",
             account.get('name') or account_id,
             len(groups), time.time() - t)


def get_session(role, region, session_name="c7n-log-exporter", session=None):
    if role == 'self':
        session = boto3.Session()
    elif isinstance(role, str):
        session = assumed_session(role, session_name, region=region)
    elif isinstance(role, list):
        session = None
        for r in role:
            session = assumed_session(r, session_name, session=session, region=region)
    else:
        session = boto3.Session()
    return session


def filter_group_names(groups, patterns):
    """Filter log groups by shell patterns.
    """
    group_names = [g['logGroupName'] for g in groups]
    matched = set()
    for p in patterns:
        matched.update(fnmatch.filter(group_names, p))
    return [g for g in groups if g['logGroupName'] in matched]


def filter_creation_date(groups, start, end):
    """Filter log groups by their creation date.

    Also sets group specific value for start to the minimum
    of creation date or start.
    """
    results = []
    for g in groups:
        created = datetime.fromtimestamp(g['creationTime'] / 1000.0)
        if created > end:
            continue
        if created > start:
            g['exportStart'] = created
        else:
            g['exportStart'] = start
        results.append(g)
    return results


def filter_last_write(client, groups, start):
    """Filter log groups where the last write was before the start date.
    """
    retry = get_retry(('ThrottlingException',))

    def process_group(group_set):
        matched = []
        for g in group_set:
            streams = retry(
                client.describe_log_streams,
                logGroupName=g['logGroupName'],
                orderBy='LastEventTime',
                limit=1, descending=True)
            if not streams.get('logStreams'):
                continue
            stream = streams['logStreams'][0]
            if stream['storedBytes'] == 0 and datetime.fromtimestamp(
                    stream['creationTime'] / 1000) > start:
                matched.append(g)
            elif 'lastIngestionTime' in stream and datetime.fromtimestamp(
                    stream['lastIngestionTime'] / 1000) > start:
                matched.append(g)
        return matched

    results = []

    with ThreadPoolExecutor(max_workers=3) as w:
        futures = {}
        for group_set in chunks(groups, 10):
            futures[w.submit(process_group, group_set)] = group_set

        for f in as_completed(futures):
            if f.exception():
                log.error(
                    "Error processing groupset:%s error:%s",
                    group_set,
                    f.exception())
            results.extend(f.result())

    return results


def filter_extant_exports(client, bucket, prefix, days, start, end=None):
    """Filter days where the bucket already has extant export keys.
    """
    end = end or datetime.now()
    # days = [start + timedelta(i) for i in range((end-start).days)]
    try:
        tag_set = client.get_object_tagging(Bucket=bucket, Key=prefix).get('TagSet', [])
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchKey':
            raise
        tag_set = []
    tags = {t['Key']: t['Value'] for t in tag_set}

    if 'LastExport' not in tags:
        return sorted(days)
    last_export = parse(tags['LastExport'])
    if last_export.tzinfo is None:
        last_export = last_export.replace(tzinfo=tzutc())
    return [d for d in sorted(days) if d > last_export]


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('-r', '--region', multiple=False)
def access(config, region, accounts=()):
    """Check iam permissions for log export access in each account"""
    config = validate.callback(config)
    accounts_report = []

    def check_access(account):
        accounts_report.append(account)
        session = get_session(account['role'], region)
        identity = session.client('sts').get_caller_identity()
        account['account_id'] = identity['Account']
        account.pop('groups')
        account.pop('role')
        client = session.client('iam')
        policy_arn = identity['Arn']
        if policy_arn.count('/') > 1:
            policy_arn = policy_arn.rsplit('/', 1)[0]
        if ':sts:' in policy_arn:
            policy_arn = policy_arn.replace(':sts', ':iam')
        if ':assumed-role' in policy_arn:
            policy_arn = policy_arn.replace(':assumed-role', ':role')
        evaluation = client.simulate_principal_policy(
            PolicySourceArn=policy_arn,
            ActionNames=['logs:CreateExportTask'])['EvaluationResults']
        account['access'] = evaluation[0]['EvalDecision']

    with ThreadPoolExecutor(max_workers=16) as w:
        futures = {}
        for account in config.get('accounts', ()):
            if accounts and account['name'] not in accounts:
                continue
            futures[w.submit(check_access, account)] = None
        for f in as_completed(futures):
            pass
    accounts_report.sort(key=operator.itemgetter('access'), reverse=True)
    print(tabulate(accounts_report, headers='keys'))


def GetHumanSize(size, precision=2):
    # interesting discussion on 1024 vs 1000 as base
    # https://en.wikipedia.org/wiki/Binary_prefix
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    suffixIndex = 0
    while size > 1024:
        suffixIndex += 1
        size = size / 1024.0

    return "%.*f %s" % (precision, size, suffixes[suffixIndex])


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('--day', required=True, help="calculate sizes for this day")
@click.option('--group', required=True)
@click.option('--human/--no-human', default=True)
@click.option('-r', '--region', multiple=False)
def size(config, accounts=(), day=None, group=None, human=True, region=None):
    """size of exported records for a given day."""
    config = validate.callback(config)
    destination = config.get('destination')
    client = boto3.Session().client('s3')
    day = parse(day)

    def export_size(client, account):
        paginator = client.get_paginator('list_objects_v2')
        count = 0
        size = 0
        session = get_session(account['role'], region)
        account_id = session.client('sts').get_caller_identity()['Account']
        prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id
        prefix = "%s/%s/%s" % (prefix, group, day.strftime("%Y/%m/%d"))
        account['account_id'] = account_id
        for page in paginator.paginate(
                Bucket=destination['bucket'],
                Prefix=prefix):
            for k in page.get('Contents', ()):
                size += k['Size']
                count += 1
        return (count, size)

    total_size = 0
    accounts_report = []
    logging.getLogger('botocore').setLevel(logging.ERROR)
    with ThreadPoolExecutor(max_workers=16) as w:
        futures = {}
        for account in config.get('accounts'):
            if accounts and account['name'] not in accounts:
                continue
            futures[w.submit(export_size, client, account)] = account

        for f in as_completed(futures):
            account = futures[f]
            count, size = f.result()
            account.pop('role')
            account.pop('groups')
            total_size += size
            if human:
                account['size'] = GetHumanSize(size)
            else:
                account['size'] = size
            account['count'] = count
            accounts_report.append(account)

    accounts_report.sort(key=operator.itemgetter('count'), reverse=True)
    print(tabulate(accounts_report, headers='keys'))
    log.info("total size:%s", GetHumanSize(total_size))


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('-g', '--group', required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('-r', '--region', multiple=False)
@click.option('--dryrun/--no-dryrun', is_flag=True, default=False)
def sync(config, group, accounts=(), dryrun=False, region=None):
    """sync last recorded export to actual

    Use --dryrun to check status.
    """
    config = validate.callback(config)
    destination = config.get('destination')
    client = boto3.Session().client('s3')

    for account in config.get('accounts', ()):
        if accounts and account['name'] not in accounts:
            continue

        session = get_session(account['role'], region)
        account_id = session.client('sts').get_caller_identity()['Account']
        prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id
        prefix = "%s/%s" % (prefix, group)

        exports = get_exports(client, destination['bucket'], prefix + "/")

        role = account.pop('role')
        if isinstance(role, str):
            account['account_id'] = role.split(':')[4]
        else:
            account['account_id'] = role[-1].split(':')[4]
        account.pop('groups')

        if exports:
            last_export = exports.pop()
            account['export'] = last_export
        else:
            account['export'] = 'missing'
            last_export = None
        try:
            tag_set = client.get_object_tagging(
                Bucket=destination['bucket'], Key=prefix).get('TagSet', [])
        except ClientError:
            tag_set = []

        tags = {t['Key']: t['Value'] for t in tag_set}
        tagged_last_export = None

        if 'LastExport' in tags:
            le = parse(tags['LastExport'])
            tagged_last_export = (le.year, le.month, le.day)
            account['sync'] = tagged_last_export
        else:
            account['sync'] = account['export'] != 'missing' and 'sync' or 'missing'

        if last_export is None:
            continue

        if tagged_last_export == last_export or account['export'] == 'missing':
            continue

        if dryrun:
            continue

        client.put_object(
            Bucket=destination['bucket'],
            Key=prefix,
            Body=json.dumps({}),
            ACL="bucket-owner-full-control",
            ServerSideEncryption="AES256")

        export_time = datetime.now().replace(tzinfo=tzlocal()).astimezone(tzutc())
        export_time = export_time.replace(
            year=last_export[0], month=last_export[1], day=last_export[2],
            minute=0, second=0, microsecond=0, hour=0)
        client.put_object_tagging(
            Bucket=destination['bucket'], Key=prefix,
            Tagging={
                'TagSet': [{
                    'Key': 'LastExport',
                    'Value': export_time.isoformat()}]})

    accounts_report = []
    for a in config.get('accounts'):
        if accounts and a['name'] not in accounts:
            continue
        if isinstance(a['sync'], tuple):
            a['sync'] = "%s/%s/%s" % (a['sync'])
        if isinstance(a['export'], tuple):
            a['export'] = "%s/%s/%s" % (a['export'])
        accounts_report.append(a)

    accounts_report.sort(key=operator.itemgetter('export'), reverse=True)
    print(tabulate(accounts_report, headers='keys'))


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('-g', '--group', required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('-r', '--region', multiple=False)
def status(config, group, accounts=(), region=None):
    """report current export state status"""
    config = validate.callback(config)
    destination = config.get('destination')
    client = boto3.Session().client('s3')

    for account in config.get('accounts', ()):
        if accounts and account['name'] not in accounts:
            continue

        session = get_session(account['role'], region)
        account_id = session.client('sts').get_caller_identity()['Account']
        prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id
        prefix = "%s/flow-log" % prefix

        role = account.pop('role')
        if isinstance(role, str):
            account['account_id'] = role.split(':')[4]
        else:
            account['account_id'] = role[-1].split(':')[4]

        account.pop('groups')

        try:
            tag_set = client.get_object_tagging(
                Bucket=destination['bucket'], Key=prefix).get('TagSet', [])
        except ClientError:
            account['export'] = 'missing'
            continue
        tags = {t['Key']: t['Value'] for t in tag_set}

        if 'LastExport' not in tags:
            account['export'] = 'empty'
        else:
            last_export = parse(tags['LastExport'])
            account['export'] = last_export.strftime('%Y/%m/%d')

    accounts = [a for a in config.get('accounts') if a in accounts or not accounts]
    accounts.sort(key=operator.itemgetter('export'), reverse=True)
    print(tabulate(accounts, headers='keys'))


def get_exports(client, bucket, prefix, latest=True):
    """Find exports for a given account
    """
    keys = client.list_objects_v2(
        Bucket=bucket, Prefix=prefix, Delimiter='/').get('CommonPrefixes', [])
    found = []
    years = []
    for y in keys:
        part = y['Prefix'].rsplit('/', 2)[-2]
        if not part.isdigit():
            continue
        year = int(part)
        years.append(year)

    if not years:
        return []

    years.sort(reverse=True)
    if latest:
        years = [years[0]]

    for y in years:
        keys = client.list_objects_v2(
            Bucket=bucket, Prefix="%s/%d/" % (prefix.strip('/'), y),
            Delimiter='/').get('CommonPrefixes', [])
        months = []
        for m in keys:
            part = m['Prefix'].rsplit('/', 2)[-2]
            if not part.isdigit():
                continue
            month = int(part)
            date_key = (y, month)
            months.append(month)
        months.sort(reverse=True)
        if not months:
            continue
        if latest:
            months = [months[0]]
        for m in months:
            keys = client.list_objects_v2(
                Bucket=bucket, Prefix="%s/%d/%s/" % (
                    prefix.strip('/'), y, ('%d' % m).rjust(2, '0')),
                Delimiter='/').get('CommonPrefixes', [])
            for d in keys:
                part = d['Prefix'].rsplit('/', 2)[-2]
                if not part.isdigit():
                    continue
                day = int(part)
                date_key = (y, m, day)
                found.append(date_key)
    found.sort(reverse=True)
    if latest:
        found = [found[0]]
    return found


@cli.command()
@click.option('--group', required=True, help="log group to export to s3.")
@click.option('--bucket', required=True, help="s3 bucket name export to.")
@click.option('--prefix', help="name of the tag to filter with using get_object_tagging API.")
@click.option('--start', required=True, help="export logs from this date")
@click.option('--end', help="export logs before this date")
@click.option('--role', help="sts role to assume for log group access")
@click.option('--poll-period', type=float, default=300)
@click.option('-r', '--region', multiple=False, help='aws region to use.')
# @click.option('--bucket-role', help="role to scan destination bucket")
# @click.option('--stream-prefix)
@lambdafan
def export(group, bucket, prefix, start, end, role, poll_period=120,
           session=None, name="", region=None):
    """export a given log group to s3"""
    start = start and isinstance(start, str) and parse(start) or start
    end = (end and isinstance(start, str) and
           parse(end) or end or datetime.now())
    start = start.replace(tzinfo=tzlocal()).astimezone(tzutc())
    end = end.replace(tzinfo=tzlocal()).astimezone(tzutc())

    if session is None:
        session = get_session(role, region)

    client = session.client('logs')

    paginator = client.get_paginator('describe_log_groups')
    for p in paginator.paginate():
        found = False
        for _group in p['logGroups']:
            if _group['logGroupName'] == group:
                group = _group
                found = True
                break
        if found:
            break

    if not found:
        raise ValueError("Log group %s not found." % group)

    if prefix:
        prefix = "%s/%s" % (prefix.rstrip('/'), group['logGroupName'].strip('/'))
    else:
        prefix = group['logGroupName']

    named_group = "%s:%s" % (name, group['logGroupName'])
    log.info(
        "Log exporting group:%s start:%s end:%s bucket:%s prefix:%s size:%s",
        named_group,
        start.strftime('%Y/%m/%d'),
        end.strftime('%Y/%m/%d'),
        bucket,
        prefix,
        group['storedBytes'])

    t = time.time()
    days = [(
        start + timedelta(i)).replace(minute=0, hour=0, second=0, microsecond=0)
        for i in range((end - start).days)]
    day_count = len(days)
    s3 = boto3.Session().client('s3')
    days = filter_extant_exports(s3, bucket, prefix, days, start, end)

    log.info("Group:%s filtering s3 extant keys from %d to %d start:%s end:%s",
             named_group, day_count, len(days),
             days[0] if days else '', days[-1] if days else '')
    t = time.time()

    retry = get_retry(('SlowDown',))

    for idx, d in enumerate(days):
        date = d.replace(minute=0, microsecond=0, hour=0)
        export_prefix = "%s%s" % (prefix, date.strftime("/%Y/%m/%d"))
        params = {
            'taskName': "%s-%s" % ("c7n-log-exporter",
                                   date.strftime("%Y-%m-%d")),
            'logGroupName': group['logGroupName'],
            'fromTime': int(time.mktime(
                date.replace(
                    minute=0, microsecond=0, hour=0).timetuple()) * 1000),
            'to': int(time.mktime(
                date.replace(
                    minute=59, hour=23, microsecond=0).timetuple()) * 1000),
            'destination': bucket,
            'destinationPrefix': export_prefix
        }

        # if stream_prefix:
        #    params['logStreamPrefix'] = stream_prefix
        try:
            s3.head_object(Bucket=bucket, Key=prefix)
        except ClientError as e:
            if e.response['Error']['Code'] != '404':  # Not Found
                raise
            s3.put_object(
                Bucket=bucket,
                Key=prefix,
                Body=json.dumps({}),
                ACL="bucket-owner-full-control",
                ServerSideEncryption="AES256")

        t = time.time()
        counter = 0
        while True:
            counter += 1
            try:
                result = client.create_export_task(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == 'LimitExceededException':
                    time.sleep(poll_period)
                    # log every 30m of export waiting
                    if counter % 6 == 0:
                        log.debug(
                            "group:%s day:%s waiting for %0.2f minutes",
                            named_group, d.strftime('%Y-%m-%d'),
                            (counter * poll_period) / 60.0)
                    continue
                raise
            retry(
                s3.put_object_tagging,
                Bucket=bucket, Key=prefix,
                Tagging={
                    'TagSet': [{
                        'Key': 'LastExport',
                        'Value': d.isoformat()}]})
            break

        log.info(
            "Log export time:%0.2f group:%s day:%s bucket:%s prefix:%s task:%s",
            time.time() - t,
            named_group,
            d.strftime("%Y-%m-%d"),
            bucket,
            params['destinationPrefix'],
            result['taskId'])

    log.info(
        ("Exported log group:%s time:%0.2f days:%d start:%s"
         " end:%s bucket:%s prefix:%s"),
        named_group,
        time.time() - t,
        len(days),
        start.strftime('%Y/%m/%d'),
        end.strftime('%Y/%m/%d'),
        bucket,
        prefix)


if __name__ == '__main__':
    cli()
