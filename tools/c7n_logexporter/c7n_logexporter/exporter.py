# Copyright 2016 Capital One Services, LLC
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

import boto3
import click
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
import time
import os
import yaml

logging.basicConfig(level=logging.INFO)
logging.getLogger('c7n.worker').setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)

log = logging.getLogger('c7n-log-exporter')


CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/schema#',
    'id': 'http://schema.cloudcustodian.io/v0/logexporter.json',
    'definitions': {
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
                'role': {'type': 'string'},
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
        'destination': {'$ref': '#/definitions/destination'}
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


@cli.command()
@click.option('--config', type=click.Path(), required=True)
@click.option('--start', required=True)
@click.option('--end')
@debug
def run(config, start, end):
    config = validate.callback(config)
    destination = config.get('destination')
    start = start and parse(start) or start
    end = end and parse(end) or datetime.now()
    for account in config.get('accounts', ()):
        process_account(account, start, end, destination)


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
def process_account(account, start, end, destination, incremental=True):
    session = get_session(account['role'])
    client = session.client('logs')

    paginator = client.get_paginator('describe_log_groups')
    groups = []
    for p in paginator.paginate():
        groups.extend([g for g in p.get('logGroups', ())])

    group_count = len(groups)
    groups = filter_creation_date(
        filter_group_names(groups, account['groups']),
        start, end)

    if incremental:
        groups = filter_last_write(client, groups, start)

    account_id = session.client('sts').get_caller_identity()['Account']
    prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id

    log.info("account:%s matched %d groups of %d",
             account.get('name', account_id),
             len(groups), group_count)

    t = time.time()
    with ThreadPoolExecutor(max_workers=3) as w:
        futures = []
        for g in groups:
            futures.append(
                w.submit(
                    export.callback,
                    g,
                    destination['bucket'], prefix,
                    g['exportStart'], end, account['role']))
        for f in as_completed(futures):
            if f.exception():
                log.error(
                    "Error processing group:%s error:%s",
                    g, f.exception())
            f.result()

    log.info("account:%s exported %d log groups in time:%0.2f",
             account.get('name') or account_id,
             len(groups),
             time.time() - t)


def get_session(role, session_name="c7n-log-exporter"):
    if role == 'self':
        session = boto3.Session()
    elif role:
        session = assumed_session(role, session_name)
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
    periods = {(d.year, d.month, d.day): d for d in days}

    keys = client.list_objects_v2(
        Bucket=bucket, Prefix=prefix, Delimiter='/').get('CommonPrefixes', [])

    years = []
    for y in keys:
        part = y['Prefix'].rsplit('/', 1)[-1]
        if not part.isdigit():
            continue
        year = int(part)
        if year < start or year > end:
            continue
        years.append(int(year))

    for y in years:
        keys = client.list_objects_v2(
            Bucket=bucket, Prefix="%s/%s" % (prefix.strip('/'), str(y)),
            Delimiter='/').get('CommonPrefixes', [])
        months = []
        for m in keys:
            part = m['Prefix'].rsplit('/', 1)[-1]
            if not part.isdigit():
                continue
            month = int(part)
            date_key = (y, month)
            if (date_key < (start.year, start.month) or
                    date_key > (end.year, end.month)):
                continue
            months.append(month)

        for m in months:
            keys = client.list_objects_v2(
                Bucket=bucket, Prefix="%s/%s/%s" % (prefix.strip('/'), y, m),
                Delimiter='/').get('CommonPrefixes', [])
            for d in keys:
                part = d['Prefix'].rsplit('/', 1)[-1]
                if not part.isdigit():
                    continue
                day = int(part)
                date_key = (y, m, day)
                if date_key in periods:
                    periods.pop(date_key)

    return sorted(periods.values())


@cli.command()
@click.option('--group', required=True)
@click.option('--bucket', required=True)
@click.option('--prefix')
@click.option('--start', required=True, help="export logs from this date")
@click.option('--end')
@click.option('--role', help="sts role to assume for log group access")
# @click.option('--period', type=float)
# @click.option('--bucket-role', help="role to scan destination bucket")
# @click.option('--stream-prefix)
@lambdafan
def export(group, bucket, prefix, start, end, role, session=None):
    start = start and isinstance(start, basestring) and parse(start) or start
    end = (end and isinstance(start, basestring) and
           parse(end) or end or datetime.now())
    start = start.replace(tzinfo=tzlocal()).astimezone(tzutc())
    end = end.replace(tzinfo=tzlocal()).astimezone(tzutc())

    if session is None:
        session = get_session(role)

    client = session.client('logs')
    retry = get_retry(('LimitExceededException',), min_delay=4)

    if prefix:
        prefix = "%s/%s" % (prefix.rstrip('/'),
                            group['logGroupName'].strip('/'))
    else:
        prefix = group

    log.debug("Log exporting group:%s start:%s end:%s bucket:%s prefix:%s",
              group,
              start.strftime('%Y/%m/%d'),
              end.strftime('%Y/%m/%d'),
              bucket,
              prefix)

    t = time.time()
    days = [start + timedelta(i) for i in range((end - start).days)]
    day_count = len(days)
    days = filter_extant_exports(
        boto3.Session().client('s3'), bucket, prefix, days, start, end)

    log.debug("Filtering s3 extant keys from %d to %d in %0.2f",
              day_count, len(days), time.time() - t)
    t = time.time()

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

        result = retry(client.create_export_task, **params)
        log.debug("Log export group:%s day:%s bucket:%s prefix:%s task:%s",
                  group,
                  params['taskName'],
                  bucket,
                  params['destinationPrefix'],
                  result['taskId'])

    log.info(("Exported log group:%s time:%0.2f days:%d start:%s"
              " end:%s bucket:%s prefix:%s"),
             group,
             time.time() - t,
             idx,
             start.strftime('%Y/%m/%d'),
             end.strftime('%Y/%m/%d'),
             bucket,
             prefix)


if __name__ == '__main__':
    cli()
