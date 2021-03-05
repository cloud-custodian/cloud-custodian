# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Salactus, eater of s3 buckets.
"""
from collections import Counter
import csv
from datetime import datetime
import functools
import json
import logging
import operator
import time

import click
import jsonschema

from rq.job import Job
from rq.registry import FinishedJobRegistry, StartedJobRegistry
from rq.queue import Queue, FailedQueue
from rq.worker import Worker
import tabulate

from c7n.config import Bag
from c7n import utils
from c7n_salactus import worker, db

# side-effect serialization patches...
try:
    from c7n_salactus import rqworker # NOQA F401
    HAVE_BIN_LIBS = True
except ImportError:
    # we want the cli to work in lambda and we might not package up
    # the relevant binaries libs (lz4, msgpack) there.
    HAVE_BIN_LIBS = False


CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/schema#',
    'id': 'http://schema.cloudcustodian.io/v0/salactus.json',
    'definitions': {

        'encrypt-keys': {
            'type': 'object',
            'required': ['type'],
            'properties': {
                'type': {'type': 'string', 'enum': ['encrypt-keys']},
                'report-only': {'type': 'boolean'},
                'glacier': {'type': 'boolean'},
                'key-id': {'type': 'string'},
                'crypto': {'type': 'string', 'enum': ['AES256', 'aws:kms']}
            }
        },

        'inventory': {
            'type': 'object',
            'properties': {
                'role': {
                    'description': "".join([
                        'The role to assume when loading inventory data ',
                        'if omitted, the master role for salactus will be used ',
                        'assuming centralized inventory collection. If empty ',
                        'it will use the salactus role in the account, else assume ',
                        'the role arn specified from the target account role.']),
                    'type': 'string'},
                'id-selector': {
                    'description': (
                        'Only use inventories with the given id.'),
                    'default': 'salactus',
                    'type': 'string'},
            }
        },

        'object-reporting': {
            'type': 'object',
            'required': ['bucket'],
            'properties': {
                'bucket': {'type': 'string'},
                'prefix': {'type': 'string'},
                'role': {'type': 'string'}
            }
        },

        'object-acl': {
            'type': 'object',
            'required': ['type'],
            'properties': {
                'type': {'type': 'string', 'enum': ['object-acl']},
                'report-only': {'type': 'boolean'},
                'allow-log': {'type': 'boolean'},
                'whitelist-accounts': {'type': 'array', 'item': {'type': 'string'}},
                # 'allow-permissions': {'type': 'array', 'item': {'type': 'string', 'enum': ''}}
            }
        },


        'visitor': {
            'type': 'object',
            'oneOf': [
                {'$ref': '#/definitions/object-acl'},
                {'$ref': '#/definitions/encrypt-keys'}
            ],
        },

        'account': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['role', 'account-id', 'name'],
            'properties': {
                'name': {'type': 'string'},
                'account-id': {'type': 'string'},
                'canonical-id': {'type': 'string'},
                'role': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}}
            },
        },
    },
    'type': 'object',
    'addditionalProperties': False,
    'required': ['accounts'],
    'properties': {
        'visitors': {
            'type': 'array',
            'items': {'$ref': '#/definitions/visitor'}
        },

        'accounts': {
            'type': 'array',
            'items': {'$ref': '#/definitions/account'}
        },
    }
}


def debug(f):
    def _f(*args, **kw):
        try:
            f(*args, **kw)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            import traceback, sys, pdb
            traceback.print_exc()
            pdb.post_mortem(sys.exc_info()[-1])
    functools.update_wrapper(_f, f)
    return _f


@click.group()
def cli():
    """Salactus, eater of s3 buckets"""


@cli.command()
@click.option('--config', help='config file for accounts/buckets', type=click.Path())
def validate(config):
    """Validate a configuration file."""
    with open(config) as fh:
        data = utils.yaml_load(fh.read())
        jsonschema.validate(data, CONFIG_SCHEMA)


@cli.command()
@click.option('--config', help='config file for accounts/buckets', type=click.Path())
@click.option('--tag', help='filter accounts by tag')
@click.option('--account', '-a',
              help='scan only the given accounts', multiple=True)
@click.option('--bucket', '-b',
              help='scan only the given buckets', multiple=True)
@click.option('--not-account',
              help='exclude the given accounts from scan', multiple=True)
@click.option('--not-bucket',
              help='exclude the given buckets from scan', multiple=True)
@click.option('--debug', is_flag=True, default=False,
              help='synchronous scanning, no workers')
@click.option('--region', multiple=True,
              help='limit scanning to specified regions')
def run(config, tag, bucket, account, not_bucket, not_account, debug, region):
    """Run across a set of accounts and buckets."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(level=logging.WARNING)

    if debug:
        def invoke(f, *args, **kw):
            # if f.func_name == 'process_keyset':
            #    key_count = len(args[-1])
            #    print("debug skip keyset %d" % key_count)
            #    return
            return f(*args, **kw)
        worker.invoke = invoke

    with open(config) as fh:
        data = utils.yaml_load(fh.read())
        for account_info in data.get('accounts', ()):
            if tag and tag not in account_info.get('tags', ()):
                continue
            if account and account_info['name'] not in account:
                continue
            if not_account and account_info['name'] in not_account:
                continue
            if 'inventory' in data and 'inventory' not in account_info:
                account_info['inventory'] = data['inventory']
            if 'visitors' in data and 'visitors' not in account_info:
                account_info['visitors'] = data['visitors']
            if 'object-reporting' in data and 'object-reporting' not in account_info:
                account_info['object-reporting'] = data['object-reporting']
                account_info['object-reporting'][
                    'record-prefix'] = datetime.utcnow().strftime('%Y/%m/%d')
            if bucket:
                account_info['buckets'] = bucket
            if not_bucket:
                account_info['not-buckets'] = not_bucket
            if region:
                account_info['regions'] = region

            try:
                worker.invoke(worker.process_account, account_info)
            except Exception:
                if not debug:
                    raise
                import pdb, traceback, sys
                traceback.print_exc()
                pdb.post_mortem(sys.exc_info()[-1])
                raise


@cli.command()
@click.option('--dbpath', help='path to json file', type=click.Path())
def save(dbpath):
    """Save the current state to a json file
    """
    d = db.db()
    d.save(dbpath)


@cli.command()
# todo check redis version if >=4 support this
# @click.option('--async/--sync', default=False)
def reset(c7n_async=None):
    """Delete all persistent cluster state.
    """
    click.echo('Delete db? Are you Sure? [yn] ', nl=False)
    c = click.getchar()
    click.echo()
    if c == 'y':
        click.echo('Wiping database')
        worker.connection.flushdb()
    elif c == 'n':
        click.echo('Abort!')
    else:
        click.echo('Invalid input :(')


@cli.command()
def workers():
    """Show information on salactus workers. (slow)"""
    counter = Counter()
    for w in Worker.all(connection=worker.connection):
        for q in w.queues:
            counter[q.name] += 1
    import pprint
    pprint.pprint(dict(counter))


def format_accounts_csv(accounts, fh):
    field_names = ['name', 'matched', 'percent_scanned', 'scanned',
                   'size', 'bucket_count']

    totals = Counter()
    skip = {'name', 'percent_scanned'}
    for a in accounts:
        for n in field_names:
            if n in skip:
                continue
            totals[n] += getattr(a, n)
    totals['name'] = 'Total'

    writer = csv.DictWriter(fh, fieldnames=field_names, extrasaction='ignore')
    writer.writerow(dict(zip(field_names, field_names)))
    writer.writerow(totals)

    for a in accounts:
        ad = {n: getattr(a, n) for n in field_names}
        writer.writerow(ad)


def format_accounts_plain(accounts, fh):
    def _repr(a):
        return "name:%s, matched:%d percent:%0.2f scanned:%d size:%d buckets:%d" % (
            a.name,
            a.matched,
            a.percent_scanned,
            a.scanned,
            a.size,
            len(a.buckets))

    for a in accounts:
        click.echo(_repr(a))


@cli.command()
@click.option('--dbpath', '-f', help='json stats db')
@click.option('--output', '-o', type=click.File('wb'), default='-',
              help="file to to output to (default stdout)")
@click.option('--format', help="format for output",
              type=click.Choice(['plain', 'csv']), default='plain')
@click.option('--account', '-a',
              help="stats on a particular account", multiple=True)
@click.option('--config', '-c',
              help="config file for accounts")
@click.option('--tag', help="filter tags by account")
@click.option('--tagprefix', help="group accounts by tag prefix")
@click.option('--region', '-r',
              help="only consider buckets from the given region",
              multiple=True)
@click.option('--not-region',
              help="only consider buckets not from the given region",
              multiple=True)
@click.option('--not-bucket',
              help="Exclude bucket", multiple=True)
def accounts(dbpath, output, format, account,
             config=None, tag=None, tagprefix=None, region=(),
             not_region=(), not_bucket=None):
    """Report on stats by account"""
    d = db.db(dbpath)
    accounts = d.accounts()
    formatter = (
        format == 'csv' and format_accounts_csv or format_accounts_plain)

    if region:
        for a in accounts:
            a.buckets = [b for b in a.buckets if b.region in region]
        accounts = [a for a in accounts if a.bucket_count]

    if not_region:
        for a in accounts:
            a.buckets = [b for b in a.buckets if b.region not in not_region]
        accounts = [a for a in accounts if a.bucket_count]

    if not_bucket:
        for a in accounts:
            a.buckets = [b for b in a.buckets if b.name not in not_bucket]
    if config and tagprefix:
        account_map = {account.name: account for account in accounts}

        with open(config) as fh:
            account_data = json.load(fh).get('accounts')
        tag_groups = {}
        for a in account_data:
            if tag is not None and tag not in a['tags']:
                continue

            for t in a['tags']:
                if t.startswith(tagprefix):
                    tvalue = t[len(tagprefix):]
                    if not tvalue:
                        continue
                    if tvalue not in tag_groups:
                        tag_groups[tvalue] = db.Account(tvalue, [])
                    account_results = account_map.get(a['name'])
                    if not account_results:
                        print("missing %s" % a['name'])
                        continue
                    tag_groups[tvalue].buckets.extend(
                        account_map[a['name']].buckets)
        accounts = tag_groups.values()

    formatter(accounts, output)


def format_plain(buckets, fh, keys=(), explicit_only=False):
    field_names = [
        'account', 'name', 'region', 'percent_scanned', 'matched',
        'scanned', 'size', 'keys_denied', 'error_count', 'partitions', 'inventory']

    if explicit_only:
        field_names = keys
    else:
        for k in keys:
            field_names.insert(0, k)

    def _repr(b):
        return [getattr(b, k) for k in field_names]

    click.echo(
        tabulate.tabulate(
            map(_repr, buckets),
            headers=keys,
            tablefmt='plain'))


def format_csv(buckets, fh, keys=()):
    field_names = ['account', 'name', 'region', 'created', 'matched', 'scanned',
                   'size', 'keys_denied', 'error_count', 'partitions', 'inventory']
    for k in keys:
        field_names.insert(0, k)

    totals = Counter()
    skip = {'account', 'name', 'region', 'percent', 'created', 'inventory'}
    skip.update(keys)

    for b in buckets:
        for n in field_names:
            if n in skip:
                continue
            totals[n] += getattr(b, n)
    totals['account'] = 'Total'
    totals['name'] = ''

    writer = csv.DictWriter(fh, fieldnames=field_names, extrasaction='ignore')
    writer.writerow(dict(zip(field_names, field_names)))
    writer.writerow(totals)

    for b in buckets:
        bd = {n: getattr(b, n) for n in field_names}
        writer.writerow(bd)


@cli.command()
@click.option('--dbpath', '-f', help="json stats db")
@click.option('--output', '-o', type=click.File('wb'), default='-',
              help="file to to output to (default stdout)")
@click.option('--format', help="format for output",
              type=click.Choice(['plain', 'csv']), default='plain')
@click.option('--bucket', '-b',
              help="stats on a particular bucket", multiple=True)
@click.option('--account', '-a',
              help="stats on a particular account", multiple=True)
@click.option('--matched', is_flag=True,
              help="filter to buckets with matches")
@click.option('--kdenied', is_flag=True,
              help="filter to buckets w/ denied key access")
@click.option('--denied', is_flag=True,
              help="filter to buckets denied access")
@click.option('--errors', is_flag=True,
              help="filter to buckets with errors")
@click.option('--size', type=int,
              help="filter to buckets with at least size")
@click.option('--incomplete', type=int,
              help="filter to buckets not scanned fully")
@click.option('--oversize', is_flag=True, help="scan count > size")
@click.option('--region',
              help="filter to buckets in region", multiple=True)
@click.option('--not-region',
              help="filter to buckets in region", multiple=True)
@click.option('--inventory',
              help="filter to buckets using inventory", is_flag=True)
@click.option('--config', type=click.Path(),
              help="config file for accounts")
@click.option('--sort',
              help="sort output by column")
@click.option('--tagprefix',
              help="include account tag value by prefix")
@click.option('--not-bucket',
              help="Exclude bucket", multiple=True)
def buckets(bucket=None, account=None, matched=False, kdenied=False,
            errors=False, dbpath=None, size=None, denied=False,
            format=None, incomplete=False, oversize=False, region=(),
            not_region=(), inventory=None, output=None, config=None, sort=None,
            tagprefix=None, not_bucket=None):
    """Report on stats by bucket"""

    d = db.db(dbpath)

    if tagprefix and not config:
        raise ValueError(
            "account tag value inclusion requires account config file")

    if config and tagprefix:
        with open(config) as fh:
            data = json.load(fh).get('accounts')
            account_data = {}
            for a in data:
                for t in a['tags']:
                    if t.startswith(tagprefix):
                        account_data[a['name']] = t[len(tagprefix):]

    buckets = []
    for b in sorted(d.buckets(account),
                    key=operator.attrgetter('bucket_id')):
        if bucket and b.name not in bucket:
            continue
        if not_bucket and b.name in not_bucket:
            continue
        if matched and not b.matched:
            continue
        if kdenied and not b.keys_denied:
            continue
        if errors and not b.error_count:
            continue
        if size and b.size < size:
            continue
        if inventory and not b.using_inventory:
            continue
        if denied and not b.denied:
            continue
        if oversize and b.scanned <= b.size:
            continue
        if incomplete and b.percent_scanned >= incomplete:
            continue
        if region and b.region not in region:
            continue
        if not_region and b.region in not_region:
            continue
        if tagprefix:
            setattr(b, tagprefix[:-1], account_data[b.account])
        buckets.append(b)

    if sort:
        key = operator.attrgetter(sort)
        buckets = list(reversed(sorted(buckets, key=key)))
    formatter = format == 'csv' and format_csv or format_plain
    keys = tagprefix and (tagprefix[:-1],) or ()
    formatter(buckets, output, keys=keys)


@cli.command(name="watch")
@click.option('--limit', default=50)
def watch(limit):
    """watch scan rates across the cluster"""
    period = 5.0
    prev = db.db()
    prev_totals = None

    while True:
        click.clear()
        time.sleep(period)
        cur = db.db()
        cur.data['gkrate'] = {}
        progress = []
        prev_buckets = {b.bucket_id: b for b in prev.buckets()}

        totals = {'scanned': 0, 'krate': 0, 'lrate': 0, 'bucket_id': 'totals'}

        for b in cur.buckets():
            if not b.scanned:
                continue

            totals['scanned'] += b.scanned
            totals['krate'] += b.krate
            totals['lrate'] += b.lrate

            if b.bucket_id not in prev_buckets:
                b.data['gkrate'][b.bucket_id] = b.scanned / period
            elif b.scanned == prev_buckets[b.bucket_id].scanned:
                continue
            else:
                b.data['gkrate'][b.bucket_id] = (
                    b.scanned - prev_buckets[b.bucket_id].scanned) / period
            progress.append(b)

        if prev_totals is None:
            totals['gkrate'] = '...'
        else:
            totals['gkrate'] = (totals['scanned'] - prev_totals['scanned']) / period
        prev = cur
        prev_totals = totals

        progress = sorted(progress, key=lambda x: x.gkrate, reverse=True)

        if limit:
            progress = progress[:limit]

        progress.insert(0, Bag(totals))
        format_plain(
            progress, None,
            explicit_only=True,
            keys=['bucket_id', 'scanned', 'gkrate', 'lrate', 'krate'])


@cli.command(name='inspect-partitions')
@click.option('-b', '--bucket', required=True)
def inspect_partitions(bucket):
    """Discover the partitions on a bucket via introspection.

    For large buckets which lack s3 inventories, salactus will attempt
    to process objects in parallel on the bucket by breaking the bucket
    into a separate keyspace partitions. It does this with a heurestic
    that attempts to sample the keyspace and determine appropriate subparts.

    This command provides additional visibility into the partitioning of
    a bucket by showing how salactus would partition a given bucket.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(level=logging.WARNING)

    state = db.db()
    # add db.bucket accessor
    found = None
    for b in state.buckets():
        if b.name == bucket:
            found = b
            break
    if not found:
        click.echo("no bucket named: %s" % bucket)
        return

    keyset = []
    partitions = []

    def process_keyset(bid, page):
        keyset.append(len(page))

    def process_bucket_iterator(bid, prefix, delimiter="", **continuation):
        partitions.append(prefix)

    # synchronous execution
    def invoke(f, *args, **kw):
        return f(*args, **kw)

    # unleash the monkies ;-)
    worker.connection.hincrby = lambda x, y, z: True
    worker.invoke = invoke
    worker.process_keyset = process_keyset
    worker.process_bucket_iterator = process_bucket_iterator

    # kick it off
    worker.process_bucket_partitions(b.bucket_id)

    keys_scanned = sum(keyset)
    click.echo(
        "Found %d partitions %s keys scanned during partitioning" % (
            len(partitions), keys_scanned))
    click.echo("\n".join(partitions))


@cli.command(name='inspect-bucket')
@click.option('-b', '--bucket', required=True)
def inspect_bucket(bucket):
    """Show all information known on a bucket."""
    state = db.db()
    found = None
    for b in state.buckets():
        if b.name == bucket:
            found = b
    if not found:
        click.echo("no bucket named: %s" % bucket)
        return

    click.echo("Bucket: %s" % found.name)
    click.echo("Account: %s" % found.account)
    click.echo("Region: %s" % found.region)
    click.echo("Created: %s" % found.created)
    click.echo("Size: %s" % found.size)
    click.echo("Inventory: %s" % found.inventory)
    click.echo("Partitions: %s" % found.partitions)
    click.echo("Scanned: %0.2f%%" % found.percent_scanned)
    click.echo("")
    click.echo("Errors")

    click.echo("Denied: %s" % found.keys_denied)
    click.echo("BErrors: %s" % found.error_count)
    click.echo("KErrors: %s" % found.data['keys-error'].get(found.bucket_id, 0))
    click.echo("Throttle: %s" % found.data['keys-throttled'].get(found.bucket_id, 0))
    click.echo("Missing: %s" % found.data['keys-missing'].get(found.bucket_id, 0))
    click.echo("Session: %s" % found.data['keys-sesserr'].get(found.bucket_id, 0))
    click.echo("Connection: %s" % found.data['keys-connerr'].get(found.bucket_id, 0))
    click.echo("Endpoint: %s" % found.data['keys-enderr'].get(found.bucket_id, 0))


@cli.command(name='inspect-queue')
@click.option('--queue', required=True)
@click.option(
    '--state', default='running',
    type=click.Choice(['running', 'pending', 'failed', 'finished']))
@click.option('--limit', default=40)
@click.option('--bucket', default=None)
def inspect_queue(queue, state, limit, bucket):
    """Show contents of a queue."""
    if not HAVE_BIN_LIBS:
        click.echo("missing required binary libs (lz4, msgpack)")
        return

    conn = worker.connection

    def job_row(j):
        if isinstance(j.args[0], basestring):  # noqa: F821
            account, bucket = j.args[0].split(':', 1)
        elif isinstance(j.args[0], dict):
            account, bucket = j.args[0]['name'], "set %d" % len(j.args[1])

        row = {
            'account': account,
            'bucket': bucket,
            # 'region': j.args[1]['region'],
            # 'size': j.args[1]['keycount'],
            'ttl': j.ttl,
            'enqueued': j.enqueued_at,
            'rtt': j.result_ttl,
            'timeout': j.timeout}

        if queue != "bucket-keyset-scan":
            row['args'] = j.args[2:]
        if state in ('running', 'failed', 'finished'):
            row['started'] = j.started_at
        if state in ('finished', 'failed'):
            row['ended'] = j.ended_at
        return row

    if state == 'running':
        registry_class = StartedJobRegistry
    elif state == 'pending':
        registry_class = Queue
    elif state == 'failed':
        registry_class = FailedQueue
    elif state == 'finished':
        registry_class = FinishedJobRegistry
    else:
        raise ValueError("invalid state: %s" % state)

    registry = registry_class(queue, connection=conn)
    records = []
    for jid in registry.get_job_ids():
        j = Job.fetch(jid, conn)
        if bucket:
            if j.args[1]['name'] != bucket:
                continue
        records.append(job_row(j))
        if len(records) == limit:
            break
    if records:
        click.echo(
            tabulate.tabulate(
                records,
                "keys",
                tablefmt='simple'))
    else:
        click.echo("no queue items found")


@cli.command()
def queues():
    """Report on progress by queues."""
    conn = worker.connection
    failure_q = None

    def _repr(q):
        return "running:%d pending:%d finished:%d" % (
            StartedJobRegistry(q.name, conn).count,
            q.count,
            FinishedJobRegistry(q.name, conn).count)
    for q in Queue.all(conn):
        if q.name == 'failed':
            failure_q = q
            continue
        click.echo("%s %s" % (q.name, _repr(q)))
    if failure_q:
        click.echo(
            click.style(failure_q.name, fg='red') + ' %s' % _repr(failure_q))


@cli.command()
def failures():
    """Show any unexpected failures"""
    if not HAVE_BIN_LIBS:
        click.echo("missing required binary libs (lz4, msgpack)")
        return

    q = Queue('failed', connection=worker.connection)
    for i in q.get_job_ids():
        j = q.job_class.fetch(i, connection=q.connection)
        click.echo("%s on %s" % (j.func_name, j.origin))
        if not j.func_name.endswith('process_keyset'):
            click.echo("params %s %s" % (j._args, j._kwargs))
        click.echo(j.exc_info)


if __name__ == '__main__':
    cli()
