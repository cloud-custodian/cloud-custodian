# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

__author__ = "Kapil Thangavelu <kapil.foss@gmail.com>"

import boto3
import click
from c7n.credentials import SessionFactory
from c7n.sqsexec import MessageIterator
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timedelta
from dateutil.parser import parse as date_parse
import gzip
import json
import logging
import multiprocessing
import os
import sqlite3
import time
import yaml

from .constants import RESOURCE_KEY, REGION_KEY
from .metrics import Resource
from .utils import human_size, unwrap, get_dates

log = logging.getLogger('zerodark.ipdb')

APP_TAG = os.environ.get('APP_TAG', 'app')
ENV_TAG = os.environ.get('ENV_TAG', 'env')
CONTACT_TAG = os.environ.get('CONTACT_TAG', 'contact')


def download_config(
        client, bucket, prefix, account_id, region, day, store, rtypes=()):
    config_prefix = "%sAWSLogs/%s/Config/%s/%s/ConfigHistory/" % (
        prefix,
        account_id,
        region,
        day.strftime('%Y/%-m/%-d'))

    results = client.list_objects_v2(
        Bucket=bucket,
        Prefix=config_prefix)

    if not os.path.exists(store):
        os.makedirs(store)

    files = []
    downloads = Counter()

    for k in results.get('Contents', ()):
        found = False
        for rt in rtypes:
            if rt in k['Key']:
                found = True
        if not found:
            continue
        fname = k['Key'].rsplit('/', 1)[-1]
        fpath = os.path.join(store, fname)
        files.append(fpath)
        if os.path.exists(fpath):
            downloads['Cached'] += 1
            downloads['CacheSize'] += k['Size']
            continue
        downloads['Downloads'] += 1
        downloads['DownloadSize'] += k['Size']
        client.download_file(bucket, k['Key'], fpath)

    log.debug(
        "Downloaded:%d Size:%d Cached:%d Size:%s Prefix:%s",
        downloads['Downloads'],
        downloads['DownloadSize'],
        downloads['Cached'],
        downloads['CacheSize'],
        config_prefix)
    return files, downloads


def process_account_resources(
        account_id, bucket, prefix, region,
        store, start, end, resource='NetworkInterface'):

    client = boto3.client('s3')
    files = []
    t = time.time()
    period_stats = Counter()
    period = (end - start).days
    resource = RESOURCE_MAPPING[resource]
    for i in range(period):
        day = start + timedelta(i)
        d_files, stats = download_config(
            client, bucket, prefix, account_id, region, day, store,
            rtypes=(resource,))
        files.extend(d_files)
        period_stats.update(stats)
    period_stats['FetchTime'] = int(time.time() - t)
    return files, period_stats


def resource_info(eni_cfg):
    desc = eni_cfg.get('description')
    instance_id = eni_cfg['attachment'].get('instanceId', '')
    if instance_id:
        rtype = RESOURCE_KEY['ec2']
        rid = instance_id
    elif desc.startswith('ELB app/'):
        rtype = RESOURCE_KEY["alb"]
        rid = desc.split('/')[1]
    elif desc.startswith('ELB net/'):
        rtype = RESOURCE_KEY["nlb"]
        rid = desc.split('/')[1]
    elif desc.startswith('ELB '):
        rtype = RESOURCE_KEY['elb']
        rid = desc.split(' ', 1)[1]
    elif desc.startswith('AWS ElasticMapReduce'):
        rtype = RESOURCE_KEY['emr']
        rid = desc.rsplit(' ', 1)[1]
    elif desc.startswith('AWS created network interface for directory'):
        rtype = RESOURCE_KEY['dir']
        rid = desc.rsplit(' ', 1)[1]
    elif desc.startswith('AWS Lambda VPC ENI:'):
        rtype = RESOURCE_KEY['lambda']
        rid = eni_cfg['requesterId'].split(':', 1)[1]
    elif desc == 'RDSNetworkInterface':
        rtype = RESOURCE_KEY['rds']
        rid = ''
    elif desc == 'RedshiftNetworkInterface':
        rtype = RESOURCE_KEY['redshift']
        rid = ''
    elif desc.startswith('ElastiCache '):
        rtype = RESOURCE_KEY['elasticache']
        rid = desc.split(' ', 1)[1]
    elif desc.startswith('ElastiCache+'):
        rtype = RESOURCE_KEY['elasticache']
        rid = desc.split('+', 1)[1]
    elif desc.startswith('Interface for NAT Gateway '):
        rtype = RESOURCE_KEY['nat']
        rid = desc.rsplit(' ', 1)[1]
    elif desc.startswith('EFS mount target'):
        rtype = RESOURCE_KEY['efs-mount']
        fsid, fsmd = desc.rsplit(' ', 2)[1:]
        rid = "%s:%s" % (fsid, fsmd[1:-1])
    elif desc.startswith('CloudHSM Managed Interface'):
        rtype = RESOURCE_KEY['hsm']
        rid = ''
    elif desc.startswith('CloudHsm ENI '):
        rtype = RESOURCE_KEY['hsmv2']
        rid = desc.rsplit(' ', 1)[1]
    elif desc == 'DMSNetworkInterface':
        rtype = RESOURCE_KEY['dms']
        rid = ''
    elif desc.startswith('DAX '):
        rtype = RESOURCE_KEY['dax']
        rid = desc.rsplit(' ', 1)[1]
    elif desc.startswith('arn:aws:ecs:'):
        # a running task with attached net
        # 'arn:aws:ecs:us-east-1:0111111111110:attachment/37a927f2-a8d1-46d7-8f96-d6aef13cc5b0'
        # also has public ip.
        rtype = RESOURCE_KEY['ecs']
        rid = desc.rsplit('/', 1)[1]
    elif desc.startswith('VPC Endpoint Interface'):
        # instanceOwnerId: amazon-aws
        # interfaceType: 'vpc_endpoint'
        rtype = RESOURCE_KEY['vpce']
        rid = desc.rsplit(' ', 1)[1]
    elif eni_cfg['attachment']['instanceOwnerId'] == 'aws-lambda':
        rtype = RESOURCE_KEY['lambda']
        rid = eni_cfg['requesterId'].split(':', 1)[1]
    else:
        rtype = RESOURCE_KEY['unknown']
        rid = json.dumps(eni_cfg)
    return rtype, rid


def resource_config_iter(files, batch_size=10000):
    for f in files:
        with gzip.open(f) as fh:
            data = json.load(fh)
        for config_set in chunks(data['configurationItems'], batch_size):
            yield config_set


def record_stream_filter(record_stream, record_filter, batch_size=5000):
    batch = []
    for record_set in record_stream:
        for r in record_set:
            if record_filter(r):
                batch.append(r)
            if len(batch) % batch_size == 0:
                yield batch
                batch = []
    if batch:
        yield batch


EBS_SCHEMA = """
create table if not exists ebs (
   volume_id text primary key,
   instance_id text,
   account_id  text,
   region      text,
   app         text,
   env         text,
   contact     text,
   start       text,
   end         text
)
"""


def index_ebs_files(db, record_stream):
    stats = Counter()
    t = time.time()
    with sqlite3.connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute(EBS_SCHEMA)
        rows = []
        deletes = {}
        skipped = 0
        for record_set in record_stream:
            for cfg in record_set:
                stats['Records'] += 1
                stats['Record%s' % cfg['configurationItemStatus']] += 1
                if cfg['configurationItemStatus'] in ('ResourceDeleted',):
                    deletes[cfg['resourceId']] = cfg['configurationItemCaptureTime']
                    continue
                if not cfg['configuration'].get('attachments'):
                    skipped += 1
                    continue
                rows.append((
                    cfg['resourceId'],
                    cfg['configuration']['attachments'][0]['instanceId'],
                    cfg['awsAccountId'],
                    cfg['awsRegion'],
                    cfg['tags'].get(APP_TAG),
                    cfg['tags'].get(ENV_TAG),
                    cfg['tags'].get(CONTACT_TAG),
                    cfg['resourceCreationTime'],
                    None))
        if rows:
            for idx, r in enumerate(rows):
                if r[0] in deletes:
                    rows[idx] = list(r)
                    rows[idx][-1] = deletes[r[0]]
            cursor.executemany(
                '''insert or replace into ebs values (?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
            stats['RowCount'] += len(rows)

        log.debug("ebs stored:%d", len(rows))

    stats['RowCount'] += len(rows)
    stats['IndexTime'] = int(time.time() - t)
    return stats


EC2_SCHEMA = """
create table if not exists ec2 (
           instance_id    text primary key,
           account_id     text,
           region         text,
           ip_address     text,
           app            text,
           env            text,
           contact        text,
           asg            text,
           start      datetime,
           end        datetime
"""


def index_ec2_files(db, record_stream):
    stats = Counter()
    t = time.time()
    with sqlite3.connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute(EC2_SCHEMA)
        rows = []
        deletes = []
        for record_set in record_stream:
            for cfg in record_set:
                stats['Records'] += 1
                stats['Record%s' % cfg['configurationItemStatus']] += 1
                if cfg['configurationItemStatus'] in ('ResourceDeleted',):
                    deletes.append(((
                        cfg['configurationItemCaptureTime'], cfg['resourceId'])))
                    continue
                if not cfg.get('tags'):
                    continue
                rows.append((
                    cfg['resourceId'],
                    cfg['awsAccountId'],
                    cfg['awsRegion'],
                    cfg['configuration'].get('privateIpAddress', ''),
                    cfg['tags'].get(APP_TAG),
                    cfg['tags'].get(ENV_TAG),
                    cfg['tags'].get(CONTACT_TAG),
                    cfg['tags'].get('aws:autoscaling:groupName', ''),
                    cfg['resourceCreationTime'],
                    None))

                if len(rows) % 1000 == 0:
                    stats['RowCount'] += len(rows)
                    cursor.executemany(
                        '''insert or replace into ec2 values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        rows)
                    rows = []
        if deletes:
            log.info("Delete count %d", len(deletes))
            stmt = 'update ec2 set end = ? where instance_id = ?'
            for p in deletes:
                cursor.execute(stmt, p)

        if rows:
            cursor.executemany(
                '''insert or replace into ec2 values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
        log.debug("ec2s stored:%d", len(rows))

    stats['RowCount'] += len(rows)
    stats['IndexTime'] = int(time.time() - t)
    return stats


S3_SCHEMA = """
create table if not exists buckets (
   name           text,
   account_id     text,
   region         text,
   app            text,
   env            text,
   contact        text,
   start      datetime,
   end        datetime,
   resource       text
)"""


def index_s3_files(db, record_stream):
    stats = Counter()
    t = time.time()
    with sqlite3.connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute(S3_SCHEMA)
        deletes = {}
        rows = []

        for record_set in record_stream:
            for cfg in record_set:
                stats['Records'] += 1
                stats['Record%s' % cfg['configurationItemStatus']] += 1
                if cfg['configurationItemStatus'] == 'ResourceNotRecorded':
                    continue
                if cfg['configurationItemStatus'] in ('ResourceDeleted'):
                    deletes[cfg['resourceId']] = cfg['configurationItemCaptureTime']
                    rows.append((
                        cfg['resourceId'], None, None, None, None, None, None,
                        cfg['configurationItemCaptureTime'], None))
                    continue
                rows.append((
                    cfg['resourceId'],
                    cfg['awsAccountId'],
                    cfg['awsRegion'],
                    cfg['tags'].get(APP_TAG),
                    cfg['tags'].get(ENV_TAG),
                    cfg['tags'].get(CONTACT_TAG),
                    cfg['resourceCreationTime'],
                    None,
                    json.dumps(cfg)))

            if len(rows) % 10000:
                cursor.executemany(
                    '''insert or replace into buckets values (?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
                stats['RowCount'] += len(rows)

        if rows:
            cursor.executemany(
                '''insert or replace into buckets values (?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
            stats['RowCount'] += len(rows)

    stats['IndexTime'] = int(time.time() - t)
    return stats


ELB_SCHEMA = """
create table if not exists elbs (
           name           text primary key,
           account_id     text,
           region         text,
           app            text,
           env            text,
           contact        text,
           start      datetime,
           end        datetime
)"""


def index_elb_files(db, record_stream):
    stats = Counter()
    t = time.time()
    with sqlite3.connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute(ELB_SCHEMA)
        rows = []
        deletes = {}
        for record_set in record_stream:
            for cfg in record_set:
                stats['Records'] += 1
                stats['Record%s' % cfg['configurationItemStatus']] += 1
                if cfg['configurationItemStatus'] in ('ResourceDeleted',):
                    deletes[cfg['resourceId']] = cfg['configurationItemCaptureTime']
                    continue
                rows.append((
                    cfg['resourceName'],
                    cfg['awsAccountId'],
                    cfg['awsRegion'],
                    cfg['tags'].get(APP_TAG),
                    cfg['tags'].get(ENV_TAG),
                    cfg['tags'].get(CONTACT_TAG),
                    cfg['resourceCreationTime'],
                    None))

        if rows:
            for idx, r in enumerate(rows):
                if r[0] in deletes:
                    rows[idx] = list(r)
                    rows[idx][-1] = deletes[r[0]]
            cursor.executemany(
                '''insert or replace into elbs values (?, ?, ?, ?, ?, ?, ?, ?)''', rows)
            stats['RowCount'] += len(rows)

        log.debug("elbs stored:%d", len(rows))

    stats['RowCount'] += len(rows)
    stats['IndexTime'] = int(time.time() - t)
    return stats


ENI_SCHEMA = """
create table if not exists enis (
          eni_id        text primary key,
          ip_address    text,
          account_id    text,
          resource_id   text,
          resource_type integer,
          subnet_id     text,
          region     integer,
          start     datetime,
          end       datetime
)"""


def index_eni_files(db, record_stream):
    stats = Counter()
    t = time.time()
    with sqlite3.connect(db) as conn:
        cursor = conn.cursor()
        cursor.execute(ENI_SCHEMA)
        cursor.execute('create index if not exists eni_idx on enis(ip_address)')
        rows = []
        skipped = 0
        deletes = {}
        rids = set()
        for record_set in record_stream:
            for cfg in record_set:
                stats['Records'] += 1
                stats['Record%s' % cfg['configurationItemStatus']] += 1
                if cfg['configurationItemStatus'] not in (
                        'ResourceDeleted', 'ResourceDiscovered', 'OK'):
                    raise ValueError(cfg)
                if cfg['configurationItemStatus'] in ('ResourceDeleted',):
                    deletes[cfg['resourceId']] = cfg['configurationItemCaptureTime']
                    continue
                eni = cfg['configuration']
                if 'attachment' not in eni or cfg['resourceId'] in rids:
                    skipped += 1
                    continue
                rids.add(cfg['resourceId'])
                rtype, rid = resource_info(eni)
                rows.append((
                    eni['networkInterfaceId'],
                    eni['privateIpAddress'],
                    cfg['awsAccountId'],
                    rid,
                    rtype,
                    eni['subnetId'],
                    REGION_KEY[cfg['awsRegion']],
                    eni['attachment'].get('attachTime') or cfg['configurationItemCaptureTime'],
                    None))

        log.debug(
            "Records:%d Insert:%d Deletes:%d Skipped:%d Discovered:%d Deleted:%d Ok:%d",
            stats['Records'], len(rows), len(deletes), skipped,
            stats['RecordResourceDiscovered'], stats['RecordResourceDeleted'],
            stats['RecordOK'])

        if rows:
            for idx, r in enumerate(rows):
                if r[0] in deletes:
                    rows[idx] = list(r)
                    rows[idx][-1] = deletes[r[0]]
                    del deletes[r[0]]
            try:
                cursor.executemany(
                    '''insert into enis values (?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
            except Exception:
                log.error("Error inserting enis account:%s rows:%d",
                          cfg['awsAccountId'], len(rows))
            stats['RowCount'] += len(rows)

    # result = cursor.execute('select count(distinct ip_address) from enis').fetchone()
    stats['SkipCount'] = skipped
    stats['IndexTime'] = int(time.time() - t)
    return stats


def chunks(iterable, size=50):
    """Break an iterable into lists of size"""
    batch = []
    for n in iterable:
        batch.append(n)
        if len(batch) % size == 0:
            yield batch
            batch = []
    if batch:
        yield batch


RESOURCE_MAPPING = {
    'Instance': 'AWS::EC2::Instance',
    'LoadBalancer': 'AWS::ElasticLoadBalancing',
    'NetworkInterface': 'AWS::EC2::NetworkInterface',
    'Volume': 'AWS::EC2::Volume',
    'Bucket': 'AWS::S3::Bucket'
}

RESOURCE_FILE_INDEXERS = {
    'Instance': index_ec2_files,
    'NetworkInterface': index_eni_files,
    'LoadBalancer': index_elb_files,
    'Volume': index_ebs_files,
    'Bucket': index_s3_files
}


@click.group()
def cli():
    """AWS Network Resource Database"""


@cli.command('worker')
@click.option('--queue')
@click.option('--s3-key')
@click.option('--period', default=60, type=click.INT)
@click.option('--verbose', default=False, is_flag=True)
def worker_config(queue, s3_key, period, verbose):
    """daemon queue worker for config notifications"""
    logging.basicConfig(level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)

    queue, region = get_queue(queue)
    factory = SessionFactory(region)
    session = factory()
    client = session.client('sqs')
    messages = MessageIterator(client, queue, timeout=20)

    for m in messages:
        msg = unwrap(m)
        if 'configurationItemSummary' in msg:
            rtype = msg['configurationItemSummary']['resourceType']
        else:
            rtype = msg['configurationItem']['resourceType']
        if rtype not in RESOURCE_MAPPING.values():
            log.info("skipping %s" % rtype)
            messages.ack(m)
        log.info("message received %s", m)


def get_queue(queue):
    if queue.startswith('https://queue.amazonaws.com'):
        region = 'us-east-1'
        queue_url = queue
    elif queue.startswith('https://sqs.'):
        region = queue.split('.', 2)[1]
        queue_url = queue
    elif queue.startswith('arn:sqs'):
        queue_arn_split = queue.split(':', 5)
        region = queue_arn_split[3]
        owner_id = queue_arn_split[4]
        queue_name = queue_arn_split[5]
        queue_url = "https://sqs.%s.amazonaws.com/%s/%s" % (
            region, owner_id, queue_name)
    return queue_url, region


@cli.command('list-app-resources')
@click.option('--app')
@click.option('--env')
@click.option('--cmdb')
@click.option('--start')
@click.option('--end')
@click.option('--tz')
@click.option(
    '-r', '--resources', multiple=True,
    type=click.Choice(['Instance', 'LoadBalancer', 'Volume']))
def list_app_resources(
        app, env, resources, cmdb, start, end, tz):
    """Analyze flow log records for application and generate metrics per period"""
    logging.basicConfig(level=logging.INFO)
    start, end = get_dates(start, end, tz)

    all_resources = []
    for rtype_name in resources:
        rtype = Resource.get_type(rtype_name)
        resources = rtype.get_resources(cmdb, start, end, app, env)
        all_resources.extend(resources)
    print(json.dumps(all_resources, indent=2))


@cli.command('load-resources')
@click.option('--bucket', required=True, help="Config Bucket")
@click.option('--prefix', required=True, help="Config Bucket Prefix")
@click.option('--region', required=True, help="Load Config for Region")
@click.option('--account-config', type=click.File('rb'), required=True)
@click.option('-a', '--accounts', multiple=True)
@click.option('--assume', help="Assume role")
@click.option('--start')
@click.option('--end')
@click.option('-r', '--resources', multiple=True,
              type=click.Choice(list(RESOURCE_FILE_INDEXERS.keys())))
@click.option('--store', type=click.Path())
@click.option('-f', '--db')
@click.option('-v', '--verbose', is_flag=True)
@click.option('--debug', is_flag=True)
def load_resources(bucket, prefix, region, account_config, accounts,
                   assume, start, end, resources, store, db, verbose, debug):
    """load resources into resource database."""
    logging.basicConfig(level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    start = date_parse(start)
    end = date_parse(end)

    if not resources:
        resources = ['NetworkInterface', 'Instance', 'LoadBalancer']

    account_map = {}
    data = yaml.safe_load(account_config.read())
    for a in data.get('accounts', ()):
        if accounts and (a['name'] in accounts or a['account_id'] in accounts):
            account_map[a['account_id']] = a
        elif not accounts:
            account_map[a['account_id']] = a
    account_ids = list(account_map)

    executor = ProcessPoolExecutor
    if debug:
        from c7n.executor import MainThreadExecutor
        MainThreadExecutor.c7n_async = False
        executor = MainThreadExecutor

    stats = Counter()
    t = time.time()
    with executor(max_workers=multiprocessing.cpu_count()) as w:
        futures = {}
        for a in account_ids:
            for r in resources:
                futures[w.submit(
                    process_account_resources, a, bucket, prefix,
                    region, store, start, end, r)] = (a, r)

        indexer = RESOURCE_FILE_INDEXERS[r]
        for f in as_completed(futures):
            a, r = futures[f]
            if f.exception():
                log.error("account:%s error:%s", a, f.exception())
                continue
            files, dl_stats = f.result()
            idx_stats = indexer(db, resource_config_iter(files))
            log.info(
                "loaded account:%s files:%d bytes:%s events:%d resources:%d idx-time:%d dl-time:%d",
                account_map[a]['name'], len(files),
                human_size(dl_stats['DownloadSize'] + dl_stats['CacheSize']),
                idx_stats['Records'],
                idx_stats['RowCount'],
                idx_stats['IndexTime'],
                dl_stats['FetchTime'])
            stats.update(dl_stats)
            stats.update(idx_stats)
    log.info("Loaded %d resources across %d accounts in %0.2f",
             stats['RowCount'], len(account_ids), time.time() - t)


if __name__ == '__main__':
    try:
        cli()
    except Exception:
        import pdb
        import traceback
        import sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
