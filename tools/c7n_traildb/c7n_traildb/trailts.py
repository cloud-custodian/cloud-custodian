# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""TrailDB to TimeSeries

Todo: Consider direct processing trails here and bypass the traildb/sqlite.
"""
from collections import defaultdict
import datetime
import logging
import os
import subprocess
import tempfile
import time

import boto3
from botocore.exceptions import ClientError
import click
from concurrent.futures import ProcessPoolExecutor, as_completed
from dateutil.parser import parse as parse_date
import jsonschema
from influxdb import InfluxDBClient
import sqlalchemy as rdb
import yaml


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s")

# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('requests').setLevel(logging.INFO)
logging.getLogger('s3transfer').setLevel(logging.INFO)
logging.getLogger('botocore.vendored').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.INFO)

log = logging.getLogger('trailidx')

CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'key_template': {'type': 'string'},
        'influx': {
            'type': 'object',
            'properties': {
                'db': {'type': 'string'},
                'host': {'type': 'string'},
                'user': {'type': 'string'},
                'password': {'type': 'string'},
            }
        },
        'accounts': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['name', 'bucket', 'regions', 'title'],
                'properties': {
                    'name': {'type': 'string'},
                    'title': {'type': 'string'},
                    'bucket': {'type': 'string'},
                    'regions': {'type': 'array', 'items': {'type': 'string'}}
                }
            }
        }
    }
}


def process_traildb(db, influx, account_name, region, since=None):
    md = rdb.MetaData(bind=db, reflect=True)
    t = md.tables['events']

    qt = time.time()
    log.debug("query account:%s region:%s services time:%0.2f incremental:%s",
              account_name, region, time.time() - qt, since)

    record_count = 0
    for b in ['console', 'program']:
        for f in ['user_id', 'event_name', 'user_agent', 'error_code']:
            if b == 'console' and f == 'user_agent':
                continue
            q = query_by(t, f, b, since=since)
            qt = time.time()
            results = q.execute().fetchall()

            log.debug(
                "query account:%s region:%s bucket:%s field:%s points:%d time:%0.2f",
                account_name, region, b, f, len(results), time.time() - qt)
            measurements = []
            for p in results:
                if f == 'user_id':
                    v = p[2].split(':', 5)[-1]
                    if '/' in v:
                        parts = v.split('/')
                        # roll up old lambda functions to their role name
                        if parts[-1].startswith('i-') or parts[-1].startswith('awslambda'):
                            v = parts[1]
                else:
                    v = p[2]
                measurements.append({
                    'measurement': '%s_%s' % (b, f),
                    'tags': {
                        'region': region,
                        'account': account_name,
                        'service': p[3],
                        'bucket': b,
                        f: v},
                    'time': '%sZ' % p[0],
                    'fields': {
                        'call_count': p[1]}})
            pt = time.time()
            influx.write_points(measurements)
            record_count += len(measurements)
            log.debug(
                "post account:%s region:%s bucket:%s field:%s points:%d time:%0.2f",
                account_name, region, b, f, len(measurements), time.time() - pt)
    return record_count


def query_by(
        t, field, bucket='console', error=False, throttle=False, since=None):

    fields = [
        rdb.func.strftime(
            "%Y-%m-%dT%H:%M", t.c.event_date).label('short_time'),
        rdb.func.count().label('call_count'),
        t.c[field],
        t.c.event_source]

    query = rdb.select(fields).group_by(
        'short_time').group_by(t.c[field]).having(
            rdb.text('call_count > 3'))

    if field == 'error_code':
        query = query.where(t.c.error_code is not None)

    query = query.group_by(t.c.event_source)

    if bucket == 'program':
        query = query.where(
            rdb.and_(
                t.c.user_agent != 'console.amazonaws.com',
                t.c.user_agent != 'console.ec2.amazonaws.com'))
    else:
        query = query.where(
            rdb.or_(
                t.c.user_agent == 'console.amazonaws.com',
                t.c.user_agent == 'console.ec2.amazonaws.com'))

    if throttle:
        query = query.where(
            rdb.or_(
                t.c.error_code == 'ThrottlingException',
                t.c.error_code == 'Client.RequestLimitExceeded'))
    elif error:
        query = query.where(
            rdb.and_(
                t.c.error_code is not None,
                rdb.or_(
                    t.c.error_code != 'ThrottlingException',
                    t.c.error_code != 'Client.RequestLimitExceeded')))

    if since:
        query = query.where(
            rdb.text("short_time > '%s'" % (since.strftime("%Y-%m-%dT%H:%M"))))

    return query


def index_account(config, region, account, day, incremental):
    log = logging.getLogger('trailidx.processor')
    influx = InfluxDBClient(
        username=config['influx']['user'],
        password=config['influx']['password'],
        database=config['influx']['db'],
        host=config['influx'].get('host'))
    s3 = boto3.client('s3')
    bucket = account.get('bucket')
    name = account.get('name')
    key_template = config.get('key_template')

    log.debug("processing account:%s region:%s day:%s",
              name, region, day.strftime("%Y/%m/%d"))

    with tempfile.NamedTemporaryFile(suffix='.db.bz2', delete=False) as fh:
        key_data = dict(account)
        key_data['region'] = region
        key_data['date_fmt'] = "%s/%s/%s" % (
            day.year, day.month, day.day)
        key = key_template % key_data
        st = time.time()

        try:
            key_info = s3.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                log.warning("account:%s region:%s missing key:%s",
                            name, region, key)
                os.remove(fh.name)
                return
            if e.response['Error']['Code'] == '403':
                msg = "account:%s region:%s forbidden key:%s" % (
                    name, region, key)
                log.warning(msg)
                raise ValueError(msg)
            raise
        s3.download_file(bucket, key, fh.name)
        log.debug("downloaded %s in %0.2f", key, time.time() - st)

        t = time.time()
        subprocess.check_call(["lbzip2", "-d", fh.name])
        log.debug("decompressed %s in %0.2f", fh.name, time.time() - t)

        t = time.time()
        since = incremental and day or None

        record_count = process_traildb(
            rdb.create_engine("sqlite:////%s" % fh.name[:-4]),
            influx, name, region, since)
        log.debug("indexed %s in %0.2f", fh.name, time.time() - t)
        os.remove(fh.name[:-4])
        log.debug("account:%s day:%s region:%s records:%d complete:%0.2f",
                  name, day.strftime("%Y-%m-%d"), region,
                  record_count,
                  time.time() - st)

    return {'time': time.time() - st, 'records': record_count, 'region': region,
            'account': name, 'day': day.strftime("%Y-%m-%d"),
            'db-date': key_info['LastModified']}


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
        return [now - datetime.timedelta(seconds=60 * 60)]

    days = []
    n_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    for n in range(1, (end - n_start).days):
        days.append(n_start + datetime.timedelta(n))
    days.insert(0, start)
    if n_start != end:
        days.append(end)

    return days


def get_incremental_starts(config, default_start):
    influx = InfluxDBClient(
        username=config['influx']['user'],
        password=config['influx']['password'],
        database=config['influx']['db'],
        host=config['influx'].get('host'))

    account_starts = {}
    for account in config.get('accounts'):
        for region in account.get('regions'):
            res = influx.query("""
                select * from program_event_name
                where account = '%s'
                  and region = '%s'
                order by time desc limit 1""" % (
                account['name'], region))
            if res is None or len(res) == 0:
                account_starts[(account['name'], region)] = default_start
                continue
            # its all utc
            account_starts[(account['name'], region)] = parse_date(
                res.raw['series'][0]['values'][0][0]).replace(tzinfo=None)

    return account_starts


@click.group()
def trailts():
    """TrailDB Time Series Index"""


@trailts.command()
@click.option('-c', '--config', required=True, help="Config file")
@click.option('-a', '--account', required=True, help="Account name")
@click.option('-d', '--day', required=True, help="Day")
@click.option('-r', '--region', required=True, help="region")
@click.option('-o', '--output', default="trail.db")
def download(config, account, day, region, output):
    """Download a traildb file for a given account/day/region"""

    with open(config) as fh:
        config = yaml.safe_load(fh.read())

    jsonschema.validate(config, CONFIG_SCHEMA)

    found = None
    for info in config['accounts']:
        if info['name'] == account:
            found = info
            break

    if not found:
        log.info("Account %s not found", account)
        return

    s3 = boto3.client('s3')
    day = parse_date(day)

    key_data = dict(found)
    key_data['region'] = region
    key_data['date_fmt'] = "%s/%s/%s" % (
        day.year, day.month, day.day)
    key = config['key_template'] % key_data

    s3.download_file(found['bucket'], key, output + '.bz2')
    subprocess.check_call(["lbzip2", "-d", output + '.bz2'])


@trailts.command()
@click.option('-c', '--config', required=True, help="Config file")
def status(config):
    """time series lastest record time by account."""
    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)
    last_index = get_incremental_starts(config, None)
    accounts = {}
    for (a, region), last in last_index.items():
        accounts.setdefault(a, {})[region] = last
    print(yaml.safe_dump(accounts, default_flow_style=False))


@trailts.command()
@click.option('-c', '--config', required=True, help="Config file")
@click.option('--start', required=True, help="Start date")
@click.option('--end', required=False, help="End Date")
@click.option('--incremental/--no-incremental', default=False,
              help="Sync from last indexed timestamp")
@click.option('--concurrency', default=5)
@click.option('-a', '--accounts', multiple=True)
@click.option('--verbose/--no-verbose', default=False)
def index(config, start, end, incremental=False, concurrency=5, accounts=None,
          verbose=False):
    """index traildbs directly from s3 for multiple accounts.

    context: assumes a daily traildb file in s3 with key path
             specified by key_template in config file for each account
    """
    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)

    if verbose:
        logging.root.setLevel(logging.DEBUG)
    log.info("tmpdir %s" % os.environ.get('TMPDIR'))

    with ProcessPoolExecutor(max_workers=concurrency) as w:
        futures = {}

        if incremental:
            account_starts = get_incremental_starts(config, start)
        else:
            account_starts = defaultdict(lambda : start) # NOQA E203

        for account in config.get('accounts'):
            if accounts and account['name'] not in accounts:
                continue
            for region in account.get('regions'):
                for d in get_date_range(
                        account_starts[(account['name'], region)], end):
                    i = bool(d.hour or d.minute)
                    p = (config, region, account, d, i)
                    futures[w.submit(index_account, *p)] = p

        for f in as_completed(futures):
            _, region, account, d, incremental = futures[f]

            result = f.result()
            if result is None:
                continue
            log.info(
                ("processed account:%(account)s day:%(day)s region:%(region)s "
                 "records:%(records)s time:%(time)0.2f db-date:%(db-date)s"
                 ) % result)


if __name__ == '__main__':
    trailts(auto_envvar_prefix='TRAIL')
