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
from c7n.utils import get_retry
import datetime
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
            },
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
            return cli()
        except SystemExit:
            raise
        except Exception:
            import traceback, pdb, sys
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
@click.option('--config', type=click.Path())
@click.option('--start', required=True)
@click.option('--end')
def run(config, start, end):
    config = validate.callback(config)
    destination = config.get('destination')
    start = start and parse(start) or start
    end = end and parse(end) or datetime.datetime.now()
    for account in config.get('accounts', ()):
        process_account(account, start, end, destination)

        
def lambdafan(func):
    """simple decorator that will auto fan out async style in lambda."""

    if not 'AWS_LAMBDA_FUNCTION_NAME' in os.environ:
        return func

    @functools.wraps(func)
    def scaleout(*args, **kw):
        client = boto3.client('lambda')
        client.invoke(
            FunctionName=os.environ['AWS_LAMBDA_FUNCTION_NAME'],
            InvocationType='Event',
            Payload=json.dumps({
                'event': 'fanout',
                'function': func.__name__,
                'args': args,
                'kwargs': kw}),
            Qualifier=os.environ['AWS_LAMBDA_FUNCTION_VERSION'])
    return scaleout


@lambdafan
def process_account(account, start, end, destination):
    session = get_session(account['role'])
    client = session.client('logs')
    
    paginator = client.get_paginator('describe_log_groups')
    group_names = []
    for p in paginator.paginate():
        group_names.extend([g['logGroupName'] for g in p.get('logGroups', ())])

    groups_creation = {g['logGroupName']: datetime.datetime.fromtimestamp(g['creationTime']/1000.0)
                       for g in p.get('logGroups', ())}
    matched_groups = set()
    for g in account['groups']:
        matched_groups.update(fnmatch.filter(group_names, g))

    account_id = session.client('sts').get_caller_identity()['Account']
    prefix = destination.get('prefix', '').rstrip('/') + '/%s' % account_id

    log.info("matched %d groups of %d", len(matched_groups), len(group_names))
    for g in matched_groups:
        group_start = start
        if group_start < groups_creation[g]:
            group_start = groups_creation[g]
        if group_start > end:
            log.info("Skipping group %s end: %s before start/creation: %s",
                     g, end.strftime('%y/%m/%d'), group_start.strftime('%Y/%m/%d'))
            continue
        export.callback(
            g,
            destination['bucket'],
            prefix,
            group_start,
            end,
            None, None, None,
            session)
            

def get_session(role, session_name="c7n-log-exporter"):
    if role == 'self':
        session = boto3.Session()
    elif role:
        session = assumed_session(role, session_name)
    else:
        session = boto3.Session()
    return session



@cli.command()
@click.option('--group', required=True)
@click.option('--bucket', required=True)
@click.option('--prefix')
@click.option('--start', required=True)
@click.option('--end')
#@click.option('--period', type=float)
@click.option('--role')
@click.option('--bucket-role', help="role to scan destination bucket")
@click.option('--task-name', default="c7n-log-exporter")
@click.option('--stream-prefix')
def export(group, bucket, prefix, start, end, role, task_name, stream_prefix, session=None):
    start = start and isinstance(start, basestring) and parse(start) or start
    end = end and isinstance(start, basestring) and parse(end) or end or datetime.datetime.now()
    start = start.replace(tzinfo=tzlocal()).astimezone(tzutc())
    end = end.replace(tzinfo=tzlocal()).astimezone(tzutc())

    if session is None:
        session = get_session(role)
    
    client = session.client('logs')
    retry = get_retry(('LimitExceededException',))

    if prefix:
        prefix = "%s/%s" % (prefix.rstrip('/'), group)
    else:
        prefix = group

    log.info("Log exporting group:%s start:%s end:%s bucket:%s prefix:%s",
             group,
             start.strftime('%Y/%m/%d'),
             end.strftime('%Y/%m/%d'),
             bucket,
             prefix)

    for d in range(abs((start-end).days)):
        date = start + datetime.timedelta(d)
        date = date.replace(minute=0, microsecond=0, hour=0)
        export_prefix = "%s%s" % (prefix, date.strftime("/%Y/%m/%d"))
            
        params = {
            'taskName': "%s-%s" % (task_name, date.strftime("%Y-%m-%d")),
            'logGroupName': group,
            'fromTime': int(time.mktime(
                date.replace(minute=0, microsecond=0, hour=0
                ).timetuple()) * 1000),
            'to': int(time.mktime(
                date.replace(minute=59, hour=23, microsecond=0
                ).timetuple()) * 1000),
            'destination': bucket,
            'destinationPrefix': export_prefix
        }

        if stream_prefix:
            params['logStreamPrefix'] = stream_prefix

        result = retry(client.create_export_task, **params)
        log.debug("Log export group:%s day:%s bucket:%s prefix:%s task:%s",
                 group,
                 params['taskName'],
                 bucket,
                 params['destinationPrefix'],
                 result['taskId'])

    
if __name__ == '__main__':
    cli()
