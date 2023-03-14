# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import click
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil.parser import parse as parse_date
from datetime import datetime, timedelta
import jsonschema
from requests.exceptions import ConnectionError
import logging
import math
import os
import sqlite3
import time
import yaml

from c7n.credentials import assumed_session
from c7n.executor import MainThreadExecutor
from c7n.utils import chunks, dumps
from c7n_org.cli import CONFIG_SCHEMA

try:
    from influxdb import InfluxDBClient
    HAVE_INFLUXDB = True
except ImportError:
    HAVE_INFLUXDB = False

log = logging.getLogger('metrics')

CONFIG_SCHEMA['properties']['indexer'] = {'type': 'object'}

MAX_RESULT_POINTS = 1440


class Resource:

    @classmethod
    def id(cls, r):
        return r[cls.mid]

    @classmethod
    def get_resources(cls, cmdb, start, end, app, env):
        with sqlite3.connect(cmdb) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                select *
                from %s
                where app = ?
                and env = ?
                and start < ?
                and (end > ? or end is null)
                ''' % cls.table,
                (app, env,
                 end.strftime('%Y-%m-%dT%H:%M'),
                 start.strftime('%Y-%m-%dT%H:%M')))
            keymeta = [v[0] for v in cursor.description]
            # todo - compare/use row factory ?
            return map(dict, map(lambda x: zip(keymeta, x), list(cursor)))

    @staticmethod
    def get_type(rtype):
        return RESOURCE_INFO[rtype]


class EC2(Resource):
    mid = 'instance_id'
    table = 'ec2'
    namespace = 'AWS/EC2'
    type = 'Instance'
    metrics = [
        dict(name='CPUUtilization'),
        dict(name='NetworkIn'),
        dict(name='NetworkOut'),
        dict(name='DiskReadOps'),
        dict(name='DiskWriteOps'),
        dict(name='DiskReadBytes'),
        dict(name='DiskWriteBytes')]

    @staticmethod
    def get_dimensions(r):
        return [{'Name': 'InstanceId', 'Value': r['instance_id']}]


class ELB(Resource):
    mid = 'name'
    table = 'elbs',
    namespace = 'AWS/ELB'
    type = 'LoadBalancer'
    metrics = [
        dict(name='HealthyHostCount'),
        dict(name='UnHealthyHostCount'),
        dict(name='BackendConnectionErrors', statistic='Sum'),
        dict(name='HTTPCode_Backend_2XX', statistic='Sum'),
        dict(name='HTTPCode_Backend_3XX', statistic='Sum'),
        dict(name='HTTPCode_Backend_4XX', statistic='Sum'),
        dict(name='HTTPCode_Backend_5XX', statistic='Sum'),
        dict(name='Latency', statistic='Average'),
        dict(name='RequestCount', statistic='Sum'),
        dict(name='SpilloverCount', statistic='Sum'),
        dict(name='SurgeQueueLength', statistic='Maximum')]

    @staticmethod
    def get_dimensions(r):
        return [{'Name': 'LoadBalancerName', 'Value': r['name']}]

#    @classmethod
#    def get_resources(cls, *args, **kw):
#        resources = super(ELB, cls).get_resources(*args, **kw)
#        filtered = set()
#        results = []
#        for r in resources:
#            if r['name'] in filtered:
#                continue
#            results.append(r)
#            filtered.add(r['name'])
#        return results


class EBS(Resource):

    mid = 'volume_id'
    table = 'ebs'
    namespace = 'AWS/EBS'
    type = 'Volume'
    metrics = [
        dict(name='VolumeReadBytes'),
        dict(name='VolumeReadOps'),
        dict(name='VolumeWriteBytes'),
        dict(name='VolumeWriteOps'),
        dict(name='VolumeTotalReadTime'),
        dict(name='VolumeTotalWriteTime'),
        dict(name='VolumeQueueLength')]

    @staticmethod
    def get_dimensions(r):
        return [{'Name': 'VolumeId', 'Value': r['volume_id']}]


RESOURCE_INFO = {
    'Instance': EC2,
    'Volume': EBS,
    'LoadBalancer': ELB}


def get_indexer(config):
    itype = config['indexer'].get('type')
    if itype == 'dir':
        return DirIndexer(config)
    elif itype == 'influx':
        return InfluxIndexer(config)
    raise ValueError("Unknown index type: %s" % itype)


class DirIndexer:

    def __init__(self, config):
        self.config = config
        self.dir = config['indexer'].get('store-dir')

    def index(self, metrics_set):
        for r, rtype, m, point_set in metrics_set:
            mdir = os.path.join(
                self.dir, r['account_id'], rtype.id(r))
            if not os.path.exists(mdir):
                os.makedirs(mdir)
            with open(os.path.join(mdir, '%s.json'), 'w') as fh:
                fh.write(dumps([r, rtype, m, point_set]))


class SQLIndexer:

    #  metadata = rdb.MetaData()
    #  table = rdb.Table(
    #        'resource_metrics',
    #        rdb.Column(),
    #        rdb.Column(),
    #        )

    def __init__(self, config):
        self.config = config
        self.engine = self.config['indexer']['dsn']


class InfluxIndexer:

    def __init__(self, config):
        self.config = config
        self.client = InfluxDBClient(
            username=self.config['indexer']['user'],
            password=self.config['indexer']['password'],
            host=self.config['indexer']['host'],
            database=self.config['indexer']['database'])

    def first(self, resource, resource_type, metric):
        mkey = ("%s_%s" % (
            resource_type.namespace.split('/')[-1],
            metric['name'])).lower()
        return self.get_resource_time(resource_type.id(resource), mkey, 'desc')

    def last(self, resource, resource_type, metric):
        mkey = ("%s_%s" % (
            resource_type.namespace.split('/')[-1],
            metric['name'])).lower()
        return self.get_resource_time(resource_type.id(resource), mkey, 'desc')

    def get_resource_time(self, rid, mkey, direction='desc'):
        result = self.client.query(
            '''select * from %s
               where ResourceId = '%s' order by time %s limit 1''' % (
                mkey, rid, direction))
        if len(result) == 0:
            return None
        return parse_date(list(result)[0][0]['time'])

    def index(self, metrics_set):
        points = []
        for r, rtype_name, m, point_set in metrics_set:
            rtype = Resource.get_type(rtype_name)
            rtags = {
                'ResourceId': rtype.id(r),
                'ResourceType': rtype.__name__,
                'AccountId': r['account_id'],
                'Region': r['region'],
                'App': r['app'],
                'Env': r['env']}
            s = m.get('statistic', 'Average')
            for p in point_set:
                p = dict(p)
                p['fields'] = {}
                p['fields'][s] = p.pop(s)
                if 'Unit' in p:
                    pu = p.pop('Unit', None)
                    if pu != 'None':
                        p['fields']['Unit'] = pu
                p['measurement'] = ("%s_%s" % (
                    rtype.namespace.split('/')[-1],
                    m['name'])).lower()
                p['time'] = p.pop('Timestamp')
                p['tags'] = rtags
                points.append(p)

        for point_set in chunks(points, 10000):
            errs = 0
            while True:
                try:
                    self.client.write_points(point_set)
                except ConnectionError:
                    errs += 1
                    if errs > 3:
                        raise
                    time.sleep(3)
                    continue
                else:
                    break

        return len(points)


def get_sessions(accounts_config, account_ids):
    sessions = {}
    for a in accounts_config.get('accounts', []):
        if a['account_id'] not in account_ids:
            continue
        session = assumed_session(a['role'], 'app-metrics')
        sessions[a['account_id']] = session
    return sessions


def get_clients(accounts_config, account_ids, regions, service='cloudwatch'):
    clients = {}
    for a in accounts_config.get('accounts', []):
        if a['account_id'] not in account_ids:
            continue
        session = assumed_session(a['role'], 'app-metrics')
        for r in regions:
            clients['%s-%s' % (
                a['account_id'], r)] = session.client(service, region_name=r)
    return clients


def get_date_ranges(start, end, period, r):
    r_start = parse_date(r['start']).replace(tzinfo=None)
    if r['end']:
        r_end = parse_date(r['end']).replace(tzinfo=None)
    else:
        r_end = end
    if r_start > start:
        start = r_start
    if r_end < end:
        end = r_end
    if r_end < start:
        return
    date_delta = (end - start)
    increments = date_delta.total_seconds() / float(period)
    if increments <= MAX_RESULT_POINTS:
        yield (start, end)
        return

    parts = date_delta.total_seconds() / (MAX_RESULT_POINTS * period)
    for i in range(int(math.ceil(parts))):
        max_period = timedelta(seconds=(MAX_RESULT_POINTS * period))
        p_start = start + max_period * i
        p_end = min(end, start + max_period * (i + 1))
        yield (p_start, p_end)


RETENTION_PERIODS = OrderedDict([
    ((0, 15), 60),
    ((15, 63), 300),
    ((63, 455), 3600)
])


def get_metric_period(start, end):
    ago = datetime.now() - start
    for (rstart, rend), rvalue in RETENTION_PERIODS.items():
        if ago.days < rend:
            return rvalue


def get_metric_tasks(indexer, resource_type, resource_set, start, end):
    tasks = []
    period = get_metric_period(start, end)
    for r in resource_set:
        dims = resource_type.get_dimensions(r)
        for m in resource_type.metrics:
            # TODO: incremental, needs more thought, this is barebones
            # but works for always forward mode, its also chatty
            # we should query out the values for the entire app's
            # resources.
            m_end = indexer.last(r, resource_type, m)
            if m_end is not None:
                m_end = m_end.replace(tzinfo=None)
                if m_end > start:
                    start = m_end
            for (start_time, end_time) in get_date_ranges(
                    start, end, period, r):
                params = dict(
                    Namespace=resource_type.namespace,
                    MetricName=m['name'],
                    Statistics=[m.get('statistic', 'Average')],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Dimensions=dims)
                tasks.append((r, resource_type.type, m, params))
    return tasks


def collect_metrics(clients, tasks):
    metrics = []
    for (resource, rtype, metric, params) in tasks:
        client = clients.get('%s-%s' % (
            resource['account_id'], resource['region']))
        points = client.get_metric_statistics(**params).get('Datapoints', [])
        # log.info("getting metrics r:%s %s %s %s points:%d",
        #          Resource.get_type(rtype).id(resource),
        #          metric['name'], params['StartTime'],
        #          params['EndTime'], len(points))
        if not points:
            continue
        metrics.append((resource, rtype, metric, points))
    return metrics


@click.command('load-app-metrics')
@click.option('--app', required=True)
@click.option('--env')
@click.option(
    '-r', '--resources', multiple=True,
    type=click.Choice(['Instance', 'LoadBalancer', 'Volume']))
@click.option('--cmdb', required=True, type=click.Path())
@click.option('--config', required=True, type=click.Path())
@click.option('--start', required=True)
@click.option('--end', required=True)
@click.option('--debug', is_flag=True)
def cli(app, env, resources, cmdb, config, start, end, debug):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(logging.WARNING)
    with open(config) as fh:
        accounts_config = yaml.safe_load(fh.read())
    jsonschema.validate(accounts_config, CONFIG_SCHEMA)

    start, end = parse_date(start), parse_date(end)
    log.info("Collecting app:%s env:%s metrics %s to %s", app, env, start, end)

    MainThreadExecutor.c7n_async = False
    executor = debug and MainThreadExecutor or ThreadPoolExecutor
    indexer = get_indexer(accounts_config)

    for rtype in resources:
        metrics_count = 0
        resource_type = RESOURCE_INFO[rtype]
        resource_set = resource_type.get_resources(cmdb, start, end, app, env)
        clients = get_clients(
            accounts_config,
            {r['account_id'] for r in resource_set},
            {r['region'] for r in resource_set})
        log.info("Found %d %s resources", len(resource_set), rtype)

        tasks = get_metric_tasks(
            indexer, resource_type, resource_set, start, end)
        log.info("Collecting metrics across %d tasks", len(tasks))
        t = time.time()
        with executor(max_workers=6) as w:
            futures = []
            for task_set in chunks(tasks, 50):
                futures.append(w.submit(collect_metrics, clients, task_set))
            for f in as_completed(futures):
                if f.exception():
                    log.warning(
                        "error processing resource set %s" % f.exception())
                    continue
                metrics_count += indexer.index(f.result())

        log.info(
            "time:%0.2f app:%s resource_type:%s points:%d start:%s end:%s",
            time.time() - t, app, rtype, metrics_count, start, end)


if __name__ == '__main__':
    try:
        cli()
    except Exception:
        import pdb, traceback, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
