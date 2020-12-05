# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""AWS AutoTag Resource Creators

See readme for details
"""

__author__ = "Kapil Thangavelu <https://twitter.com/kapilvt>"

from botocore.exceptions import ClientError
import click
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
from dateutil.parser import parse
import jmespath
import json
import jsonschema
import logging
import os
import shutil
import sqlite3
import tempfile
import time


from c7n.config import Config as ExecConfig
from c7n.credentials import SessionFactory
from c7n.policy import PolicyCollection
from c7n.resources import load_resources, aws
from c7n.tags import UniversalTag
from c7n.utils import local_session, chunks, reset_session_cache

from c7n_org.cli import WORKER_COUNT, resolve_regions, get_session, _get_env_creds, init as org_init
from c7n_org.utils import environ

try:
    from cStringIO import StringIO
except ImportError:
    from io import BytesIO as StringIO  # NOQA

from botocore.client import Config


log = logging.getLogger('c7n_trailowner')

# Globals (read-only once set), resource map
resource_map = None

# Nutshell resource schema for events is roughly equivalent
# to custodian's cloudtrail event selector.
RESOURCE_SCHEMA = {
    '$schema': 'http://json-schema.org/schema#',
    'id': 'http://schema.cloudcustodian.io/v0/trailcreator.json',
    'definitions': {
        'resource': {
            'type': 'object',
            'properties': {
                # custodian resource-type aka resource: ec2
                'resource': {
                    'type': 'string', 'description': 'custodian resource type'},
                # optional
                'shape': {'type': 'string'},
                # create events
                'events': {
                    'type': 'array',
                    'items': {'$ref': '#/definitions/event'}}
            }
        },
        # resource create event descriptor
        'event': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'event': {'type': 'string'},
                'service': {'type': 'string'},
                'ids': {'type': 'string'}}
        }
    },
    'additionalProperties': False,
    'properties': {
        'resources': {
            'type': 'array',
            'items': {'$ref': '#/definitions/resource'}
        }
    }
}


TRAIL_ATHENA_QUERY = """\
select records.awsregion as region,
       records.recipientaccountid as accountId,
       records.eventtime as eventTime,
       records.eventname as eventName,
       records.eventsource as eventSource,
       records.useragent as userAgent,
       records.sourceipaddress as sourceIPAddress,
       records.useridentity.type as userType,
       records.useridentity.arn as userArn,
       records.useridentity.username as userName,
       records.useridentity.invokedby as invokedBy,
       records.requestparameters as requestParameters,
       records.responseelements as responseElements
from "{athena_db}"."{table}" as records
where records.errorcode is null
  and records.eventname in ({events})
"""

TRAIL_S3_QUERY = """\
select records.awsRegion as region,
       records.recipientAccountId as accountId,
       records.eventTime,
       records.eventName,
       records.eventSource,
       records.userAgent,
       records.sourceIPAddress,
       records.userIdentity.type as userType,
       records.userIdentity.arn as userArn,
       records.userIdentity.userName as userName,
       records.userIdentity.invokedBy as invokedBy,
       records.userIdentity.sourceIPAddress as userIPAddress,
       records.requestParameters,
       records.responseElements
from s3object[*].Records[*] as records
where records."errorCode" is null
  and records."eventName" in ({events})
"""


def format_bytes(size):
    # 2**10 = 1024
    power = 2**10
    n = 0
    labels = {0: 'b', 1: 'Kb', 2: 'Mb', 3: 'Gb', 4: 'Tb'}
    while size > power:
        size /= power
        n += 1
    return '%0.2f %s' % (size, labels[n])


def format_record(r):
    """Format a resource creation cloud trail event for db schema
    """
    rinfos = resource_map.get((r['eventSource'], r['eventName']))
    if rinfos is None:
        log.warning(
            "Could not resolve rinfo %s %s", r['eventSource'], r['eventName'])
        return

    utype = r['userType']
    if utype == 'Root':
        uid = 'root'
    elif utype == 'SAMLUser':
        uid = r['userName']
    elif utype is None and r['invokedBy'] == 'AWS Internal':
        uid = r['userIdentity']['invokedBy']
    else:
        uid = r['userArn']

    for rinfo in rinfos:
        # todo consider lite implementation
        rid = jmespath.search(rinfo['ids'], r)
        if isinstance(rid, list):
            rid = " ,".join(rid)
        if rid:
            break
    if rid is None:
        log.warning(
            "couldn't find rids account:%s region:%s service:%s api:%s",
            r['accountId'], r['region'], r['eventSource'], r['eventName'])
        return

    return (
        r['accountId'],
        r['region'],
        r['eventTime'],
        r['eventName'],
        r['eventSource'],
        r.get('userAgent', ''),
        r['sourceIPAddress'],
        uid,
        rinfo['resource']['resource'],
        rid)


def get_stream_records(stream, delimiter, stats):
    """Extract resource creation records from s3 select statement results stream.
    """

    line_buf = ""
    for event in stream:
        if 'Stats' in event:
            stats['BytesScanned'] += event['Stats']['Details']['BytesScanned']
            stats['BytesProcessed'] += event['Stats']['Details']['BytesProcessed']
            stats['BytesReturned'] += event['Stats']['Details']['BytesReturned']

        if 'Records' not in event:
            continue

        for line in event['Records']['Payload'].decode('utf8').split(delimiter):
            if not line:
                continue

            # Record payloads can span events (we limit to one span)
            rr = None
            if line_buf:
                line = line_buf + line
                line_buf = ""
                line_buf_consume = True
            else:
                line_buf_consume = False

            try:
                rr = format_record(json.loads(line))
            except Exception:
                if line_buf_consume:
                    raise
                line_buf = line
            if not rr:
                continue
            yield rr


def process_select_set(s3, trail_bucket, object_set):
    """Query cloudtrail s3 objects for resource creation records.
    """
    global resource_map

    q = TRAIL_S3_QUERY.format(
        events="'%s'" % "', '".join({k[1] for k in resource_map}))
    stats = Counter()
    delimiter = '\n'
    resource_records = []

    for o in object_set:
        result = s3.select_object_content(
            Bucket=trail_bucket,
            Key=o['Key'],
            ExpressionType='SQL',
            InputSerialization={'CompressionType': 'GZIP', 'JSON': {'Type': 'Document'}},
            OutputSerialization={'JSON': {'RecordDelimiter': delimiter}},
            Expression=q)
        resource_records.extend(
            get_stream_records(result['Payload'], delimiter, stats))
    return {'stats': dict(stats), 'records': resource_records}


def process_athena_query(athena, workgroup, athena_db, table, athena_output,
                         db_path, query_id=None, account_id=None, poll_period=30,
                         year=None, month=None, day=None):
    q = TRAIL_ATHENA_QUERY.format(
        athena_db=athena_db,
        table=table,
        events="'%s'" % "', '".join({k[1] for k in resource_map}))

    if account_id:
        q += "and records.recipientaccountid = '{}'".format(
            account_id)

    date_format, date_value = None, None
    if year:
        date_format, date_value = "%Y", year.strftime("%Y")
    if month:
        date_format, date_value = "%Y/%m", month.strftime("%Y/%m")
    if day:
        date_format, date_value = "%Y/%m/%d", month.strftime("%Y/%m/%d")
    if date_format:
        q = q + (" AND date_format(from_iso8601_timestamp(records.eventtime), "
                 "'{date_format}') = '{date_value}'").format(
            date_format=date_format,
            date_value=date_value)

    if query_id is None:
        query_id = athena.start_query_execution(
            ResultConfiguration={'OutputLocation': athena_output,
                                 # use workload configuration to override.
                                 'EncryptionConfiguration': {
                                     'EncryptionOption': 'SSE_S3'}},
            QueryString=q,
            WorkGroup=workgroup).get('QueryExecutionId')
    stats = Counter()

    log.info("Athena query:%s", query_id)

    while True:
        qexec = athena.get_query_execution(QueryExecutionId=query_id).get('QueryExecution')
        if qexec.get('Statistics'):
            stats['QueryExecutionTime'] = qexec['Statistics'].get(
                'EngineExecutionTimeInMillis',
                qexec['Statistics'].get(
                    'TotalExecutionTimeInMillis',
                    1000
                )
            ) / 1000.0
            stats['DataScannedInBytes'] = qexec['Statistics'].get('DataScannedInBytes', 1)
            log.info(
                "Polling athena query progress scanned:%s qexec:%0.2fs",
                format_bytes(
                    stats['DataScannedInBytes']), stats['QueryExecutionTime'])
        if qexec.get('Status', {}).get('State') == 'FAILED':
            raise ValueError("Athena Query Failure: {}".format(
                qexec['Status']['StateChangeReason']))
        if qexec.get('Status', {}).get('State') != 'SUCCEEDED':
            log.debug("Next query result poll in %0.2f seconds" % (
                float(poll_period)))
            time.sleep(poll_period)
            continue
        break

    db = TrailDB(db_path)
    pager = athena.get_paginator('get_query_results')

    for page in pager.paginate(QueryExecutionId=query_id):
        headers = None
        results = []
        for row in page.get('ResultSet', {}).get('Rows', ()):
            if headers is None:
                headers = [h['VarCharValue'] for h in row['Data']]
                continue
            values = [c.get('VarCharValue', '') for c in row['Data']]
            record = dict(zip(headers, values))
            record['requestParameters'] = json.loads(record['requestParameters'])
            record['responseElements'] = json.loads(record['responseElements'])
            results.append(format_record(record))
        stats['RecordCount'] += len(results)
        log.info('processing athena result page %d records' % len(results))
        db.insert(results)
        db.flush()
    log.info("Athena Processed %d records" % stats['RecordCount'])
    return {'stats': dict(stats)}


class TrailDB:

    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.cursor = self.conn.cursor()
        self._init()

    def _init(self):
        command = '''
           create table if not exists events (
              account_id   varchar(16),
              region       varchar(16),
              event_date   datetime,
              event_name   varchar(128),
              event_source varchar(128),
              user_agent   varchar(128),
              client_ip    varchar(32),
              user_id      varchar(128),
              rtype        varchar(42),
              resource_ids varchar(256))'''
        self.cursor.execute(command)

    def insert(self, records):
        command = "insert into events values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        self.cursor.executemany(command, records)

    def flush(self):
        try:
            self.conn.commit()
        except sqlite3.OperationalError:
            time.sleep(3)
            self.conn.commit()

    def get_type_record_stats(self, account_id, region):
        self.cursor.execute('''
            select rtype, count(*) as rcount
            from events
            where account_id="%s"
              and region="%s"
            group by rtype
        ''' % (account_id, region))
        return self.cursor.fetchall()

    def get_resource_owners(self, resource_type, account_id, region):
        self.cursor.execute('''
           select user_id, resource_ids
           from events
           where rtype="%s"
             and account_id="%s"
             and region="%s"
           order by event_date
        ''' % (resource_type, account_id, region))
        return self.cursor.fetchall()


def process_bucket(session_factory, bucket_name, prefix, db_path):
    session = session_factory()
    s3 = session.client('s3', config=Config(signature_version='s3v4'))
    paginator = s3.get_paginator('list_objects')

    db = TrailDB(db_path)
    stats = Counter()
    t = time.time()
    bsize = 100
    workers = 10

    log.info("Processing workers:%d cloud-trail:%s page_size:%d", workers, prefix, bsize)
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        objects = page.get('Contents', ())
        page_stats = Counter()
        page_stats['ObjectCount'] += len(objects)
        page_stats['ObjectSize'] += sum([o['Size'] for o in objects])

        pt = time.time()

        with ThreadPoolExecutor(max_workers=workers) as w:
            futures = {}
            for page_objects in chunks(objects, bsize):
                futures[w.submit(
                    process_select_set, s3, bucket_name, page_objects)] = page_objects

            for f in as_completed(futures):
                if f.exception():
                    log.error("err processing records %s %s", f.exception(), futures[f])

                results = f.result()
                page_stats['records'] += len(results['records'])
                page_stats.update(results['stats'])
                for r in results['records']:
                    page_stats[r[-2]] += 1
                db.insert(results['records'])

            db.flush()

        log.info("Processed page time:%0.2f stats:%s", time.time() - pt, page_stats)
        if objects:
            log.info('Last Page Key: %s', objects[-1]['Key'])

        stats.update(page_stats)
    log.info("Finished %0.2f seconds stats:%s", time.time() - t, stats)


class ResourceTagger:

    def __init__(self, trail_db, exec_config, creator_tag, user_suffix, dryrun, types):
        self.trail_db = trail_db
        self.config = exec_config
        self.creator_tag = creator_tag
        self.user_suffix = user_suffix
        self.dryrun = dryrun
        self.stats = Counter()
        self.types = types

    def process(self):
        for rtype, rcount in self.trail_db.get_type_record_stats(
                self.config['account_id'], self.config['region']):
            if self.types and rtype not in self.types:
                continue
            resource_map = self.get_creator_resource_map(rtype)
            resources, rmgr = self.get_untagged_resources(rtype)

            if not len(resources):
                continue

            rtype_id = rmgr.resource_type.id
            # regroup by user/tag value to minimize api calls
            user_resources = {}
            found = 0
            for r in resources:
                if r[rtype_id] not in resource_map:
                    self.stats[rtype + '-not-found'] += 1
                    log.debug(
                        "account:%s region:%s no trail record resource:%s id:%s",
                        self.config['account_id'], self.config['region'],
                        rtype, r[rtype_id])
                    continue
                uid = resource_map[r[rtype_id]]
                user_resources.setdefault(uid, []).append(r)
                found += 1

            log.info((
                "account:%s region:%s tag %d %s resources users:%d "
                "population:%d not-found:%d records:%d"),
                self.config['account_id'], self.config['region'],
                found, rtype, len(user_resources), len(resources),
                self.stats[rtype + "-not-found"], rcount)
            self.stats[rtype] += found

            for u, resources in user_resources.items():
                try:
                    self.tag_resources(rmgr, u, resources)
                except ClientError as e:
                    log.exception(
                        "Error tagging account:%s region:%s resource:%s error:%s",
                        self.config['account_id'], self.config['region'], rtype,
                        e)
                    raise
        return self.stats

    def tag_resources(self, resource_mgr, user_id, resources):
        """Tag set of resources with user as creator.
        """
        tagger_factory = resource_mgr.action_registry['tag']
        tagger = tagger_factory({}, resource_mgr)
        client = tagger.get_client()

        tags = [{'Key': self.creator_tag, 'Value': user_id}]
        if isinstance(tagger, UniversalTag):
            tags = {self.creator_tag: user_id}
        if not self.dryrun:
            for resource_set in chunks(resources, tagger.batch_size):
                tagger.process_resource_set(client, resource_set, tags)

    def get_creator_resource_map(self, rtype):
        """Return a map of resource id to creator for the given resource type.
        """
        resource_map = {}
        for user_id, resource_ids in self.trail_db.get_resource_owners(
                rtype, self.config['account_id'], self.config['region']):
            if self.user_suffix and not user_id.endswith(self.user_suffix):
                continue
            if 'AWSServiceRole' in user_id:
                continue

            if ',' in resource_ids:
                resource_ids = [rid.strip() for rid in resource_ids.split(',')]
            else:
                resource_ids = [resource_ids]

            for rid in resource_ids:
                resource_map[rid] = user_id.rsplit('/', 1)[-1]
        return resource_map

    def get_untagged_resources(self, rtype):
        policy_data = {
            'name': 'inventory-%s' % rtype,
            'resource': rtype,
            'filters': [{
                'tag:{}'.format(
                    self.creator_tag): 'absent'}]}
        # Cloud Formation stacks can only be tagged in successful
        # steady state.
        if rtype == 'cfn':
            policy_data['filters'].insert(0, {
                'type': 'value',
                'key': 'StackStatus',
                'op': 'in',
                'value': ['UPDATE_COMPLETE', 'CREATE_COMPLETE']})

        policy = list(
            PolicyCollection.from_data(
                {'policies': [policy_data]}, self.config)).pop()
        if 'tag' not in policy.resource_manager.action_registry:
            return [], None
        resources = policy.run()
        return resources, policy.resource_manager


def get_bucket_path(prefix, account, region, day, month, year):
    prefix = "%(prefix)s/AWSLogs/%(account)s/CloudTrail/%(region)s/" % {
        'prefix': prefix.strip('/'), 'account': account, 'region': region}
    prefix = prefix.lstrip('/')
    date_prefix = None
    if day:
        date = parse(day)
        date_prefix = date.strftime("%Y/%m/%d/")
    if month:
        date = parse(month)
        date_prefix = date.strftime("%Y/%m/")
    if year:
        date = parse(year)
        date_prefix = date.strftime("%Y/")
    if date_prefix:
        prefix += date_prefix
    return prefix


def load_resource_map(resource_map_file):
    global resource_map
    data = json.load(resource_map_file)
    jsonschema.validate(data, RESOURCE_SCHEMA)
    resource_map = {}
    for r in data.get('resources', ()):
        for e in r.get('events', []):
            resource_map.setdefault(
                (e['service'], e['event']), []).append(
                    {'resource': r, 'ids': e['ids']})


@contextlib.contextmanager
def temp_dir():
    try:
        tdir = tempfile.mkdtemp()
        yield tdir
    finally:
        shutil.rmtree(tdir)


@click.group()
def cli():
    """CloudTrail Resource Creator Tagger
    """
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('custodian').setLevel(logging.ERROR)


@cli.command('load-s3')
@click.option('--bucket', required=True, help="Cloudtrail Bucket")
@click.option('--prefix', help="CloudTrail Prefix", default="")
@click.option('--account', required=True, help="Account to process trail records for")
@click.option('--region', required=True, help="Region to process trail records for")
@click.option('--resource-map', required=True,
            help="Resource map of events and id selectors", type=click.File())
@click.option('--db', required=True, help="Output DB path (sqlite)")
@click.option("--day", help="Only process trail events for the given day")
@click.option("--month", help="Only process trail events for the given month")
@click.option("--year", help="Only process trail events for the given year")
@click.option("--assume", help="Assume role for trail bucket access")
@click.option("--profile", help="AWS cli profile for trail bucket access")
def load(bucket, prefix, account, region, resource_map, db, day, month, year,
         assume, profile):
    """Ingest cloudtrail events from s3 into resource owner db.
    """
    load_resource_map(resource_map)
    prefix = get_bucket_path(prefix, account, region, day, month, year)
    session_factory = SessionFactory(region=region, profile=profile, assume_role=assume)
    process_bucket(session_factory, bucket, prefix, db)


@cli.command('load-athena')
@click.option('--account', default=None, help=(
    "Account to process trail records for, default"
    " is all accounts in the trail data"))
@click.option('--region', required=True, help="Region to process trail records for")
@click.option('--resource-map', required=True,
            help="Resource map of events and id selectors", type=click.File())
@click.option('--workgroup', default="primary",
              help="Athena Workgroup (default: primary)")
@click.option('--table', required=True, help="Cloud Trail Athena Table")
@click.option('--athena-db', default="default", help="Athena DB")
@click.option('--athena-output', help="Athena S3 Output Location")
@click.option('--query-id', help="Process results of a previous Athena query")
@click.option('--db', required=True, help="Output DB path (sqlite)")
@click.option("--day", help="Only process trail events for the given day")
@click.option("--month", help="Only process trail events for the given month")
@click.option("--year", help="Only process trail events for the given year")
@click.option("--assume", help="Assume role for trail bucket access")
@click.option("--profile", help="AWS cli profile for trail bucket access")
def load_athena(table, workgroup, athena_db, athena_output, resource_map,
                db, query_id, day, month, year, account,
                assume, profile, region):
    """Ingest cloudtrail events from athena into resource owner db.

    The athena db/tables should be created per the schema documented here.
    https://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html
    """
    load_resource_map(resource_map)
    session_factory = SessionFactory(region=region, profile=profile, assume_role=assume)
    session = session_factory()
    if athena_output is None:
        athena_account_id = session.client(
            'sts').get_caller_identity()['Account']
        athena_output = "s3://aws-athena-query-results-{}-{}".format(
            athena_account_id, session.region_name)

    process_athena_query(
        session_factory().client('athena'),
        workgroup,
        athena_db,
        table,
        db_path=db,
        athena_output=athena_output,
        query_id=query_id,
        account_id=account,
        year=year and parse(year) or None,
        month=month and parse(month) or None,
        day=day and parse(day) or None)


@cli.command()
@click.option('--config', required=True, help="c7n-org Accounts config file", type=click.Path())
@click.option('--db', required=True, help="Resource Owner DB (sqlite)", type=click.Path())
@click.option('--creator-tag', required=True, help="Tag to utilize for resource creator")
@click.option('--user-suffix', help="Ignore users without the given suffix")
@click.option('--dryrun', is_flag=True)
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('-t', '--tags', multiple=True, default=None, help="Account tag filter")
@click.option('-r', '--region', default=None, multiple=True, required=True)
@click.option('--debug', default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('--type', multiple=True, help="Only process resources of type")
def tag_org(config, db, region, creator_tag, user_suffix, dryrun,
            accounts, tags, debug, verbose, type):
    """Tag an orgs resources
    """
    accounts_config, custodian_config, executor = org_init(
        config, use=None, debug=debug, verbose=verbose,
        accounts=accounts or None, tags=tags, policies=None,
        resource=None, policy_tags=None)

    load_resources()
    stats = {}
    total = 0
    start_exec = time.time()

    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config['accounts']:
            for r in resolve_regions(region or a.get('regions', ()), a):
                futures[w.submit(
                    tag_org_account, a, r, db,
                    creator_tag, user_suffix, dryrun, type)] = (a, r)
        for f in as_completed(futures):
            a, region = futures[f]
            if f.exception():
                log.warning("error account:%s id:%s region:%s error:%s" % (
                    a['name'], a['account_id'], region, f.exception()))
                continue
            result = f.result()
            if result:
                stats[(a['name'], region)] = (a, result)
            print(
                ("auto tag complete account:%s id:%s region:%s \n  %s" % (
                    a['name'], a['account_id'], region,
                    "\n  ".join([
                        " {}: {}".format(k, v)
                        for k, v in result.items()
                        if v and not k.endswith('not-found')]))).strip())

            total += sum([
                v for k, v in result.items() if not k.endswith('not-found')])

    print("Total resources tagged: %d in %0.2f" % total, time.time() - start_exec)
    return stats


def tag_org_account(account, region, db, creator_tag, user_suffix, dryrun, type):
    log.info("processing account:%s id:%s region:%s",
             account['name'], account['account_id'], region)
    session = get_session(account, "c7n-trailcreator", region)
    env_vars = _get_env_creds(session, region)
    with environ(**env_vars):
        try:
            return tag.callback(
                None, region, db, creator_tag, user_suffix, dryrun, summary=False, type=type)
        finally:
            reset_session_cache()


@cli.command()
@click.option('--db', required=True, help="Resource Owner DB (sqlite)", type=click.Path())
@click.option('--creator-tag', required=True, help="Tag to utilize for resource creator")
@click.option('--region', required=True, help="Aws region to process")
@click.option('--assume', help="Assume role for resource tagging")
@click.option('--user-suffix', help="Ignore users without the given suffix")
@click.option('--dryrun', is_flag=True)
@click.option('--type', multiple=True, help="Only process resources of type")
@click.option("--profile", help="AWS cli profile for resource tagging")
def tag(assume, region, db, creator_tag, user_suffix, dryrun,
        summary=True, profile=None, type=()):
    """Tag resources with their creator.
    """
    trail_db = TrailDB(db)
    load_resources(resource_types=('aws.*',))

    with temp_dir() as output_dir:
        config = ExecConfig.empty(
            output_dir=output_dir, assume=assume,
            region=region, profile=profile)
        factory = aws.AWS().get_session_factory(config)
        account_id = local_session(factory).client('sts').get_caller_identity().get('Account')
        config['account_id'] = account_id
        tagger = ResourceTagger(trail_db, config, creator_tag, user_suffix, dryrun, type)

        try:
            stats = tagger.process()
        except Exception:
            log.exception(
                "error processing account:%s region:%s config:%s env:%s",
                account_id, region, config, dict(os.environ))
            raise

    if not summary:
        return stats

    log.info(
        "auto tag summary account:%s region:%s \n%s",
        config['account_id'],
        config['region'],
        "\n".join([" {}: {}".format(k, v) for k, v in stats.items() if v]))
    total = sum([v for k, v in stats.items() if not k.endswith('not-found')])
    log.info("Total resources tagged: %d" % total)
