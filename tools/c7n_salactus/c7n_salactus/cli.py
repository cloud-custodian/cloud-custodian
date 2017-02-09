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
"""Salactus, eater of s3 buckets.
"""
from __future__ import print_function

from collections import Counter
import csv
import functools
import json
import logging
import operator

import click

from rq.registry import FinishedJobRegistry, StartedJobRegistry
from rq.queue import Queue
from rq.worker import Worker

from c7n_salactus import worker, db


def debug(f):
    def _f(*args, **kw):
        try:
            f(*args, **kw)
        except (SystemExit, KeyboardInterrupt) as e:
            raise
        except:
            import traceback, sys, pdb
            traceback.print_exc()
            pdb.post_mortem(sys.exc_info()[-1])
    functools.update_wrapper(_f, f)
    return _f


@click.group()
def cli():
    """Salactus, eater of s3 buckets"""


@cli.command()
@click.option('--config', help='config file for accounts/buckets')
@click.option('--tag', help='filter accounts by tag')
@click.option('--account', '-a',
              help='scan only the given accounts', multiple=True)
@click.option('--bucket', '-b',
              help='scan only the given buckets', multiple=True)
@click.option('--debug', is_flag=True,
              help='synchronous scanning, no workers')
def run(config, tag, bucket, account, debug=False):
    """Run across a set of accounts and buckets."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
    logging.getLogger('botocore').setLevel(level=logging.WARNING)

    if debug:
        def invoke(f, *args, **kw):
            if f.func_name == 'process_keyset':
                print("skip keyset")
                return
            return f(*args, **kw)
        worker.invoke = invoke

    with open(config) as fh:
        data = json.load(fh)
        for account_info in data:
            if tag and tag not in account_info.get('tags', ()):
                continue
            if account and account_info['name'] not in account:
                continue
            if bucket:
                account_info['buckets'] = bucket
            worker.invoke(worker.process_account, account_info)


@cli.command()
@click.option('--dbpath', help='path to json file')
def save(dbpath):
    """Save the current state to a json file
    """
    d = db.db()
    d.save(dbpath)


@cli.command()
@click.option('--dbpath', help='path to json file')
def reset(dbpath):
    """Save the current state to a json file
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
    counter = Counter()
    for w in Worker.all(connection=worker.connection):
        for q in w.queues:
            counter[q.name] += 1
    import pprint
    pprint.pprint(dict(counter))


@cli.command()
@click.option('--dbpath', '-f', help='json stats db')
@click.option('--account', '-a',
              help="stats on a particular account", multiple=True)
def accounts(dbpath, account):
    """Report on stats by account"""
    d = db.db(dbpath)

    def _repr(a):
        return "name:%s, matched:%d percent:%0.2f scanned:%d size:%d buckets:%d" % (
            a.name,
            a.matched,
            a.percent_scanned,
            a.scanned,
            a.size,
            len(a.buckets))

    for a in sorted(d.accounts(), key=operator.attrgetter('name')):
        click.echo(_repr(a))


def format_plain(buckets, fh):
    def _repr(b):
        return (
            "account:%s name:%s percent:%0.2f matched:%d "
            "scanned:%d size:%d kdenied:%d errors:%d partitions:%d") % (
                b.account,
                b.name,
                b.percent_scanned,
                b.matched,
                b.scanned,
                b.size,
                b.keys_denied,
                b.error_count,
                b.partitions)
    for b in buckets:
        print(_repr(b), file=fh)


def format_csv(buckets, fh):
    field_names = ['account', 'name', 'matched', 'scanned',
                   'size', 'keys_denied', 'error_count', 'partitions']

    totals = Counter()
    skip = set(('account', 'name', 'percent'))
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
def buckets(bucket=None, account=None, matched=False, kdenied=False,
            errors=False, dbpath=None, size=None, denied=False,
            format=None, output=None):
    """Report on stats by bucket"""
    d = db.db(dbpath)

    buckets = []
    for b in sorted(d.buckets(account),
                    key=operator.attrgetter('bucket_id')):
        if bucket and b.name not in bucket:
            continue
        if matched and not b.matched:
            continue
        if kdenied and not b.keys_denied:
            continue
        if errors and not b.errors:
            continue
        if size and b.size < size:
            continue
        if denied and not b.denied:
            continue
        buckets.append(b)

    formatter = format == 'csv' and format_csv or format_plain
    formatter(buckets, output)


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
    q = Queue('failed', connection=worker.connection)
    for i in q.get_jobs():
        click.echo("%s on %s" % (i.func_name, i.origin))
        click.echo(i.exc_info)


if __name__ == '__main__':
    cli()
