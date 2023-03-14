# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import logging
import math
import random
import time

import boto3
import click
from concurrent.futures import ProcessPoolExecutor, as_completed
from dateutil.parser import parse as parse_date
from elasticsearch import Elasticsearch, helpers, RequestsHttpConnection
import jsonschema
from influxdb import InfluxDBClient

import yaml

from c7n import schema
from c7n.credentials import assumed_session, SessionFactory
from c7n.registry import PluginRegistry
from c7n.reports import csvout as s3_resource_parser
from c7n.resources import load_resources
from c7n.utils import chunks, dumps, get_retry, local_session

# from c7n.executor import MainThreadExecutor
# ThreadPoolExecutor = MainThreadExecutor
# ProcessPoolExecutor = MainThreadExecutor
# MainThreadExecutor.c7n_async = False

MAX_POINTS = 1440.0
NAMESPACE = 'CloudMaid'

log = logging.getLogger('c7n.metrics')

CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': True,
    'required': ['indexer', 'accounts'],
    'properties': {
        'indexer': {
            'oneOf': [
                {
                    'type': 'object',
                    'required': ['host', 'port', 'idx_name'],
                    'properties': {
                        'type': {'enum': ['es']},
                        'host': {'type': 'string'},
                        'port': {'type': 'number'},
                        'user': {'type': 'string'},
                        'password': {'type': 'string'},
                        'idx_name': {'type': 'string'},
                        'query': {'type': 'string'}
                    }
                },
                {
                    'type': 'object',
                    'required': ['host', 'db', 'user', 'password'],
                    'properties': {
                        'type': {'enum': ['influx']},
                        'host': {'type': 'string'},
                        'db': {'type': 'string'},
                        'user': {'type': 'string'},
                        'password': {'type': 'string'}
                    }
                },
                {
                    'type': 'object',
                    'required': ['template', 'Bucket'],
                    'properties': {
                        'type': {'enum': ['s3']},
                        'template': {'type': 'string'},
                        'Bucket': {'type': 'string'}
                    }
                }
            ]
        },
        'accounts': {
            'type': 'array',
            'items': {
                'type': 'object',
                'anyOf': [
                    {"required": ['profile']},
                    {"required": ['role']}
                ],
                'required': ['name', 'bucket', 'regions', 'title', 'id'],
                'properties': {
                    'name': {'type': 'string'},
                    'title': {'type': 'string'},
                    'tags': {'type': 'object'},
                    'bucket': {'type': 'string'},
                    'regions': {'type': 'array', 'items': {'type': 'string'}}
                }
            }
        }
    }
}

retry = get_retry(('Throttling',), log_retries=True)


indexers = PluginRegistry('policy-metrics-indexers')


class Indexer:
    """ Metrics indexer
    """


def get_indexer(config, **kwargs):
    itype = config['indexer']['type']
    klass = indexers.get(itype)
    return klass(config, **kwargs)


@indexers.register('es')
class ElasticSearchIndexer(Indexer):

    def __init__(self, config, **kwargs):
        self.config = config
        self.es_type = kwargs.get('type', 'policy-metric')

        host = [config['indexer'].get('host', 'localhost')]
        kwargs = {}
        kwargs['connection_class'] = RequestsHttpConnection

        user = config['indexer'].get('user', False)
        password = config['indexer'].get('password', False)
        if user and password:
            kwargs['http_auth'] = (user, password)

        kwargs['port'] = config['indexer'].get('port', 9200)

        self.client = Elasticsearch(
            host,
            **kwargs
        )

    def index(self, points):
        for p in points:
            p['_index'] = self.config['indexer']['idx_name']
            p['_type'] = self.es_type

        results = helpers.streaming_bulk(self.client, points)
        for status, r in results:
            if not status:
                log.debug("index err result %s", r)


@indexers.register('s3')
class S3Archiver(Indexer):

    def __init__(self, config, **kwargs):
        self.config = config
        self.client = boto3.client('s3')

    def index(self, points):
        # account, region in templ
        key = self.config['indexer']['template'].format(points[0])
        # day aggregation
        self.client.put_object(
            Bucket=self.config['indexer']['Bucket'],
            Key=key,
            Body=dumps(points))


@indexers.register('influx')
class InfluxIndexer(Indexer):

    def __init__(self, config, **kwargs):
        self.config = config
        self.client = InfluxDBClient(
            username=config['indexer']['user'],
            password=config['indexer']['password'],
            database=config['indexer']['db'],
            host=config['indexer'].get('host'))

    def index(self, points):
        measurements = []
        for p in points:
            measurements.append({
                'measurement': 'policy-metrics',
                'time': p['Timestamp'],
                'fields': {
                    'rcount': p['Sum'],
                    'runit': p['Unit']},
                'tags': {
                    'region': p['Region'],
                    'account': p['Account'],
                    'policy': p['Policy'],
                    'env': p['Env'],
                    'division': p['Division'],
                    'resource': p.get('ResType', ''),
                    'metric': p['MetricName'],
                    'namespace': p['Namespace']}})
        self.client.write_points(measurements)


def index_metric_set(indexer, account, region, metric_set, start, end, period):
    session = local_session(
        lambda : assumed_session(account['role'], 'PolicyIndex')) # NOQA E203
    client = session.client('cloudwatch', region_name=region)

    t = time.time()
    account_info = dict(account['tags'])
    account_info['Account'] = account['name']
    account_info['AccountId'] = account['id']
    account_info['Region'] = region
    point_count = 0
    for m in metric_set:
        params = dict(
            Namespace=m['Namespace'],
            MetricName=m['MetricName'],
            Statistics=['Sum'],
            Dimensions=m['Dimensions'],
            StartTime=start,
            EndTime=end,
            Period=period)
        try:
            points = retry(client.get_metric_statistics, **params)['Datapoints']
        except Exception as e:
            log.error(
                "error account:%s region:%s start:%s end:%s error:%s",
                account['name'], region, start, end, e)
        if not points:
            continue
        dims = {d['Name']: d['Value'] for d in m.pop('Dimensions', ())}
        for p in points:
            if m['Namespace'] == 'AWS/Lambda':
                dims['Policy'] = dims['FunctionName'].split('-', 1)[1]
            p.update(dims)
            p.update(m)
            p.update(account_info)
        point_count += len(points)
        log.debug("account:%s region:%s metric:%s points:%d policy:%s",
                  account['name'], region, m['MetricName'], len(points),
                  dims.get('Policy', 'unknown'))
        indexer.index(points)
    return time.time() - t, point_count


def index_account_metrics(config, idx_name, region, account, start, end, period):
    session = assumed_session(account['role'], 'PolicyIndex')
    indexer = get_indexer(config)

    client = session.client('cloudwatch', region_name=region)
    policies = set()
    account_metrics = []

    pager = client.get_paginator('list_metrics')
    for p in pager.paginate(Namespace=NAMESPACE):
        metrics = p.get('Metrics')
        for metric in metrics:
            if 'Dimensions' not in metric:
                log.warning("account:%s region:%s metric with no dims: %s",
                            account['name'], region, metric)
                continue
            dims = {d['Name']: d['Value'] for d in metric.get(
                'Dimensions', ())}
            if dims['Policy'] not in policies:
                log.debug("Processing account:%s region:%s policy: %s",
                          account['name'], region, dims['Policy'])
                policies.add(dims['Policy'])
            account_metrics.append(metric)

    for p in pager.paginate(Namespace='AWS/Lambda'):
        metrics = p.get('Metrics')
        for metric in metrics:
            dims = {d['Name']: d['Value'] for d
                    in metric.get('Dimensions', ())}
            if not dims.get('FunctionName', '').startswith('custodian-'):
                continue
            account_metrics.append(metric)

    log.debug("account:%s region:%s processing metrics:%d start:%s end:%s",
              account['name'], region, len(account_metrics),
              start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d"))

    region_time = region_points = 0

    # originally was parallel thread, but rate limits around get
    # metric stat polling means single threaded is faster.
    for metric_set in chunks(account_metrics, 20):
        mt, mp = index_metric_set(
            indexer, account, region, metric_set, start, end, period)
        region_time += mt
        region_points += mp
    log.info(("indexed account:%s region:%s metrics:%d"
              " points:%d start:%s end:%s time:%0.2f"),
             account['name'], region, len(account_metrics), region_points,
             start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d"), region_time)
    return region_time, region_points


def index_account_resources(config, account, region, policy, date):
    indexer = get_indexer(config, type=policy['resource'])
    bucket = account['bucket']
    key_prefix = "accounts/{}/{}/policies/{}".format(
        account['name'], region, policy['name'])

    # Look for AWS profile in config before Instance role
    records = s3_resource_parser.record_set(
        lambda: SessionFactory(
            region, profile=account.get('profile'),
            assume_role=account.get('role'))(),
        bucket,
        key_prefix,
        date,
        specify_hour=True)

    for r in records:
        # Adding Custodian vars to each record
        r['c7n:MatchedPolicy'] = policy['name']
        r['c7n:AccountNumber'] = account['id']

        # Reformat tags for ease of index/search
        # Tags are stored in the following format:
        # Tags: [ {'key': 'mykey', 'val': 'myval'}, {'key': 'mykey2', 'val': 'myval2'} ]
        # and this makes searching for tags difficult. We will convert them to:
        # Tags: ['mykey': 'myval', 'mykey2': 'myval2']
        r['Tags'] = {t['Key']: t['Value'] for t in r.get('Tags', [])}

    indexer.index(records)


def get_periods(start, end, period):
    days_delta = (start - end)

    period_max = (period * MAX_POINTS)
    num_periods = math.ceil(abs(days_delta.total_seconds()) / period_max)
    if num_periods <= 1:
        yield (start, end)
        return

    delta_unit = (abs(days_delta.total_seconds()) / num_periods / 86400)
    n_start = start

    for idx in range(1, int(num_periods) + 1):
        period = (n_start,
                  min((end, n_start + datetime.timedelta(delta_unit))))
        yield period
        n_start = period[1]


def get_date_range(start, end):
    if start and not isinstance(start, datetime.datetime):
        start = parse_date(start)
    if end and not isinstance(end, datetime.datetime):
        end = parse_date(end)

    now = datetime.datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0)
    if end and not start:
        raise ValueError("Missing start date")
    elif start and not end:
        end = now
    if not end and not start:
        raise ValueError("Missing start and end")
    return start, end


def valid_date(date, delta=0):
    # optional input, use default time delta if not provided
    # delta is 1 hour for resources
    if not date:
        date = datetime.datetime.utcnow() - datetime.timedelta(hours=delta)
    elif date and not isinstance(date, datetime.datetime):
        date = parse_date(date)

    return date


@click.group()
def cli():
    """Custodian Indexing"""


@cli.command(name='index-metrics')
@click.option('-c', '--config', required=True, help="Config file")
@click.option('--start', required=True, help="Start date")
@click.option('--end', required=False, help="End Date")
@click.option('--incremental/--no-incremental', default=False,
              help="Sync from last indexed timestamp")
@click.option('--concurrency', default=5)
@click.option('-a', '--accounts', multiple=True)
@click.option('-p', '--period', default=3600)
@click.option('-t', '--tag')
@click.option('--index', default='policy-metrics')
@click.option('--verbose/--no-verbose', default=False)
def index_metrics(
        config, start, end, incremental=False, concurrency=5, accounts=None,
        period=3600, tag=None, index='policy-metrics', verbose=False):
    """index policy metrics"""
    logging.basicConfig(level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('elasticsearch').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('c7n.worker').setLevel(logging.INFO)

    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)

    start, end = get_date_range(start, end)

    p_accounts = set()
    p_account_stats = {}
    i_time = i_points = 0
    t = time.time()

    with ProcessPoolExecutor(max_workers=concurrency) as w:
        futures = {}
        jobs = []
        # Filter
        for account in config.get('accounts'):
            if accounts and account['name'] not in accounts:
                continue
            if tag:
                found = False
                for t in account['tags'].values():
                    if tag == t:
                        found = True
                        break
                if not found:
                    continue
            p_accounts.add((account['name']))
            for region in account.get('regions'):
                for (p_start, p_end) in get_periods(start, end, period):
                    p = (config, index, region, account, p_start, p_end, period)
                    jobs.append(p)

        # by default we'll be effectively processing in order, but thats bumps
        # our concurrency into rate limits on metrics retrieval in a given account
        # region, go ahead and shuffle, at least with lucene, the non ordering
        # should have minimal impact on query perf (inverted index).

        random.shuffle(jobs)

        for j in jobs:
            log.debug("submit account:%s region:%s start:%s end:%s" % (
                j[3]['name'], j[2], j[4], j[5]))
            futures[w.submit(index_account_metrics, *j)] = j

        # Process completed
        for f in as_completed(futures):
            config, index, region, account, p_start, p_end, period = futures[f]
            if f.exception():
                log.warning("error account:%s region:%s error:%s",
                            account['name'], region, f.exception())
                continue
            rtime, rpoints = f.result()
            rstat = p_account_stats.setdefault(
                account['name'], {}).setdefault(region, {'points': 0})
            rstat['points'] += rpoints

            # log.info("complete account:%s, region:%s points:%s time:%0.2f",
            #         account['name'], region, rpoints, rtime)

            i_time += rtime
            i_points += rpoints

        log.info("complete accounts:%d points:%d itime:%0.2f time:%0.2f",
                 len(p_accounts), i_points, i_time, time.time() - t)


@cli.command(name='index-resources')
@click.option('-c', '--config', required=True, help="Config file")
@click.option('-p', '--policies', required=True, help="Policy file")
@click.option('--date', required=False, help="Start date")
@click.option('--concurrency', default=5)
@click.option('-a', '--accounts', multiple=True)
@click.option('-t', '--tag')
@click.option('--verbose/--no-verbose', default=False)
def index_resources(
        config, policies, date=None, concurrency=5,
        accounts=None, tag=None, verbose=False):
    """index policy resources"""
    logging.basicConfig(level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('elasticsearch').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('c7n.worker').setLevel(logging.INFO)

    # validating the config and policy files.
    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)

    with open(policies) as fh:
        policies = yaml.safe_load(fh.read())
    load_resources()
    schema.validate(policies)

    date = valid_date(date, delta=1)

    with ProcessPoolExecutor(max_workers=concurrency) as w:
        futures = {}
        jobs = []

        for account in config.get('accounts'):
            if accounts and account['name'] not in accounts:
                continue
            if tag:
                found = False
                for t in account['tags'].values():
                    if tag == t:
                        found = True
                        break
                if not found:
                    continue
            for region in account.get('regions'):
                for policy in policies.get('policies'):
                    p = (config, account, region, policy, date)
                    jobs.append(p)

        for j in jobs:
            log.debug("submit account:{} region:{} policy:{} date:{}".format(
                j[1]['name'], j[2], j[3]['name'], j[4]))
            futures[w.submit(index_account_resources, *j)] = j

        # Process completed
        for f in as_completed(futures):
            config, account, region, policy, date = futures[f]
            if f.exception():
                log.warning(
                    "error account:{} region:{} policy:{} error:{}".format(
                        account['name'], region, policy['name'], f.exception()))
                continue
            log.info("complete account:{} region:{} policy:{}".format(
                account['name'], region, policy['name']))


if __name__ == '__main__':
    try:
        cli()
    except Exception:
        import traceback, pdb, sys
        print(traceback.print_exc())
        pdb.post_mortem(sys.exc_info()[-1])
