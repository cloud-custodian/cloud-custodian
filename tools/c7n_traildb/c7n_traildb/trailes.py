# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging
import os
import subprocess
import thread

import click
from c7n.credentials import SessionFactory
from concurrent.futures import ProcessPoolExecutor, as_completed
from dateutil.parser import parse as parse_date
from elasticsearch import Elasticsearch, helpers, RequestsHttpConnection
import jsonschema
import sqlite3

import yaml

# from c7n.credentials import assumed_session, SessionFactory
from c7n.executor import ThreadPoolExecutor
from c7n.utils import local_session

log = logging.getLogger('c7n.trailes')

CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': True,
    'properties': {
        'indexer': {
            'type': 'object',
            'required': ['host', 'port', 'idx_name'],
            'properties': {
                'host': {'type': 'string'},
                'port': {'type': 'number'},
                'user': {'type': 'string'},
                'password': {'type': 'string'},
                'idx_name': {'type': 'string'},
                'query': {'type': 'string'}
            },
            'additionalProperties': True
        },
        'accounts': {
            'type': 'array',
            'items': {
                'type': 'object',
                'anyOf': [
                    {"required": ['profile']},
                    {"required": ['role']}
                ],
                'required': ['name', 'bucket', 'regions', 'title'],
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


def get_es_client(config):
    host = [config['indexer'].get('host', 'localhost')]
    es_kwargs = {}
    es_kwargs['connection_class'] = RequestsHttpConnection
    user = config['indexer'].get('user', False)
    password = config['indexer'].get('password', False)
    if user and password:
        es_kwargs['http_auth'] = (user, password)

    es_kwargs['port'] = config['indexer'].get('port', 9200)

    return Elasticsearch(host, **es_kwargs)


def index_events(client, events):
    results = helpers.streaming_bulk(client, events)
    for status, r in results:
        if not status:
            log.debug("index err result %s", r)


def dict_factory(cursor, row):
    """Returns a sqlite row factory that returns a dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def fetch_events(cursor, config, account_name):
    """Generator that returns the events"""
    query = config['indexer'].get('query',
        'select * from events where user_agent glob \'*CloudCustodian*\'')

    for event in cursor.execute(query):
        event['account'] = account_name
        event['_index'] = config['indexer']['idx_name']
        event['_type'] = config['indexer'].get('idx_type', 'traildb')
        yield event


def get_traildb(bucket, key, session_factory, directory):
    local_db_file = directory + "/traildb" + \
        str(thread.get_ident())
    local_bz2_file = local_db_file + '.bz2'

    s3 = local_session(session_factory).resource('s3')
    s3.Bucket(bucket).download_file(key['Key'], local_bz2_file)

    # Decompress the traildb file
    # (use the system bunzip2 command because it's faster than the python bzip2 library)
    subprocess.call(['bunzip2', '-f', local_bz2_file])

    return local_db_file


def valid_date(key, config_date):
    """ traildb bucket folders are not zero-padded so this validation
        checks that the keys returned by the paginator are
        *really after* the config date
    """
    key_date = "/".join(key.split("/")[4:7])
    return parse_date(key_date) > parse_date(config_date)


def index_account_trails(config, account, region, date, directory):
    es_client = get_es_client(config)

    s3 = local_session(
        lambda: SessionFactory(region, profile=account.get('profile'),
        assume_role=account.get('role'))()).client('s3')

    bucket = account['bucket']
    key_prefix = "accounts/{}/{}/traildb".format(account['name'], region)
    marker = "{}/{}/trail.db.bz2".format(key_prefix, date)

    p = s3.get_paginator('list_objects_v2').paginate(
        Bucket=bucket,
        Prefix=key_prefix,
        StartAfter=marker,
    )

    with ThreadPoolExecutor(max_workers=20) as w:
        for key_set in p:
            if 'Contents' not in key_set:
                continue
            keys = []
            for k in key_set['Contents']:
                if (k['Key'].endswith('trail.db.bz2') and valid_date(k['Key'], date)):
                    keys.append(k)

            futures = map(lambda k: w.submit(
                get_traildb, bucket, k,
                lambda: SessionFactory(region, profile=account.get('profile'),
                assume_role=account.get('role'))(), directory),
                keys)

            for f in as_completed(futures):
                local_db_file = f.result()
                connection = sqlite3.connect(local_db_file)
                connection.row_factory = dict_factory
                cursor = connection.cursor()
                index_events(es_client, fetch_events(cursor, config, account['name']))
                connection.close()

                try:
                    os.remove(local_db_file)
                except Exception:
                    log.warning("Failed to remove temporary file: {}".format(
                        local_db_file))
                    pass


def get_date_path(date, delta=0):
    # optional input, use default time delta if not provided
    # delta is 24 hours for trail
    if not date:
        date = datetime.datetime.utcnow() - datetime.timedelta(hours=delta)
    elif date and not isinstance(date, datetime.datetime):
        date = parse_date(date)

    # note that traildb doesn't use leading zero
    return date.strftime('%Y/%-m/%-d')


@click.group()
def trailes():
    """TrailDB Elastic Search"""


@trailes.command()
@click.option('-c', '--config', required=True, help="Config file")
@click.option('--date', required=False, help="Start date")
@click.option('--directory', required=False, help="Path for temp db file")
@click.option('--concurrency', default=5)
@click.option('-a', '--accounts', multiple=True)
@click.option('-t', '--tag')
@click.option('--verbose/--no-verbose', default=False)
def index(
        config, date=None, directory=None, concurrency=5, accounts=None,
        tag=None, verbose=False):
    """index traildbs directly from s3 for multiple accounts.

    context: assumes a daily traildb file in s3 with dated key path
    """

    logging.basicConfig(level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('elasticsearch').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('c7n.worker').setLevel(logging.INFO)

    with open(config) as fh:
        config = yaml.safe_load(fh.read())
    jsonschema.validate(config, CONFIG_SCHEMA)

    date = get_date_path(date, delta=24)
    directory = directory or "/tmp"

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
                p = (config, account, region, date, directory)
                jobs.append(p)

        for j in jobs:
            log.debug("submit account:{} region:{} date:{}".format(
                j[1]['name'], j[2], j[3]))
            futures[w.submit(index_account_trails, *j)] = j

        # Process completed
        for f in as_completed(futures):
            config, account, region, date, directory = futures[f]
            if f.exception():
                log.warning("error account:{} region:{} error:{}".format(
                    account['name'], region, f.exception()))
                continue
            log.info("complete account:{} region:{}".format(
                account['name'], region))


if __name__ == '__main__':
    trailes(auto_envvar_prefix='TRAIL')
