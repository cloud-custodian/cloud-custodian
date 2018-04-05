# Copyright 2017 Capital One Services, LLC
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
"""Run a custodian policy across an organization's accounts
"""

from collections import Counter
import logging
import os
import multiprocessing
import time
import subprocess

from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed)
import yaml

import boto3
from botocore.compat import OrderedDict
from botocore.exceptions import ClientError
import click
import jsonschema

from c7n.credentials import assumed_session, SessionFactory
from c7n.executor import MainThreadExecutor
from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.reports.csvout import Formatter, fs_record_set
from c7n.resources import load_resources
from c7n.manager import resources as resource_registry
from c7n.utils import CONN_CACHE, dumps

from c7n_org.utils import environ, account_tags
from c7n.utils import UnicodeWriter

log = logging.getLogger('c7n_org')


WORKER_COUNT = int(
    os.environ.get('C7N_ORG_PARALLEL', multiprocessing.cpu_count() * 4))


CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/schema#',
    'id': 'http://schema.cloudcustodian.io/v0/orgrunner.json',
    'definitions': {
        'account': {
            'type': 'object',
            'additionalProperties': True,
            'anyOf': [
                {'required': ['role', 'account_id']},
                {'required': ['profile', 'account_id']}],
            'properties': {
                'name': {'type': 'string'},
                'email': {'type': 'string'},
                'account_id': {'type': 'string'},
                'profile': {'type': 'string', 'minLength': 3},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'regions': {'type': 'array', 'items': {'type': 'string'}},
                'role': {'oneOf': [
                    {'type': 'array', 'items': {'type': 'string'}},
                    {'type': 'string', 'minLength': 3}]},
                'external_id': {'type': 'string'},
            }
        }
    },
    'type': 'object',
    'additionalProperties': False,
    'required': ['accounts'],
    'properties': {
        'vars': {'type': 'object'},
        'accounts': {
            'type': 'array',
            'items': {'$ref': '#/definitions/account'}
        }
    }
}


@click.group()
def cli():
    """custodian organization multi-account runner."""


def init(config, use, debug, verbose, accounts, tags, policies, resource=None):
    level = verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")

    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('custodian').setLevel(logging.WARNING)
    logging.getLogger('custodian.s3').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    with open(config) as fh:
        accounts_config = yaml.safe_load(fh.read())
        jsonschema.validate(accounts_config, CONFIG_SCHEMA)

    if use:
        with open(use) as fh:
            custodian_config = yaml.safe_load(fh.read())
    else:
        custodian_config = {}

    filtered_policies = []
    for p in custodian_config.get('policies', ()):
        if policies and p['name'] not in policies:
            continue
        if resource and p['resource'] != resource:
            continue
        filtered_policies.append(p)
    custodian_config['policies'] = filtered_policies

    filter_accounts(accounts_config, tags, accounts)

    load_resources()
    MainThreadExecutor.async = False
    executor = debug and MainThreadExecutor or ProcessPoolExecutor
    return accounts_config, custodian_config, executor


def resolve_regions(regions, partition='aws'):
    if 'all' in regions:
        return boto3.Session().get_available_regions('ec2', partition)
    if not regions:
        return ('us-east-1', 'us-west-2')
    return regions


def get_session(account, session_name, region):
    if account.get('role'):
        return assumed_session(account['role'], session_name, region=region, external_id=account.get('external_id'))
    elif account.get('profile'):
        return SessionFactory(region, account['profile'])()
    else:
        raise ValueError(
            "No profile or role assume specified for account %s" % account)


def filter_accounts(accounts_config, tags, accounts, not_accounts=None):
    filtered_accounts = []
    for a in accounts_config.get('accounts', ()):
        if not_accounts and a['name'] in not_accounts:
            continue
        if accounts and a['name'] not in accounts:
            continue
        if tags:
            found = set()
            for t in tags:
                if t in a.get('tags', ()):
                    found.add(t)
            if not found == set(tags):
                continue
        filtered_accounts.append(a)
    accounts_config['accounts'] = filtered_accounts


def report_account(account, region, policies_config, output_path, debug):
    cache_path = os.path.join(output_path, "c7n.cache")
    output_path = os.path.join(output_path, account['name'], region)
    config = Config.empty(
        region=region,
        output_dir=output_path,
        account_id=account['account_id'], metrics_enabled=False,
        cache=cache_path, log_group=None, profile=None, external_id=None)

    if account.get('role'):
        config['assume_role'] = account['role']
        config['external_id'] = account.get('external_id')
    elif account.get('profile'):
        config['profile'] = account['profile']

    policies = PolicyCollection.from_data(policies_config, config)
    records = []
    for p in policies:
        log.debug(
            "Report policy:%s account:%s region:%s path:%s",
            p.name, account['name'], region, output_path)
        policy_records = fs_record_set(p.ctx.output_path, p.name)
        for r in policy_records:
            r['policy'] = p.name
            r['region'] = p.options.region
            r['account'] = account['name']
            for t in account.get('tags', ()):
                if ':' in t:
                    k, v = t.split(':', 1)
                    r[k] = v
        records.extend(policy_records)
    return records


@cli.command()
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option('-f', '--output', type=click.File('w'), default='-', help="Output File")
@click.option('-u', '--use', required=True)
@click.option('-s', '--output-dir', required=True, type=click.Path())
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('--field', multiple=True)
@click.option('--no-default-fields', default=False, is_flag=True)
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('-r', '--region', default=None, multiple=True)
@click.option('--debug', default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('-p', '--policy', multiple=True)
@click.option('--format', default='csv', type=click.Choice(['csv', 'json']))
@click.option('--resource', default=None)
def report(config, output, use, output_dir, accounts,
           field, no_default_fields, tags, region, debug, verbose,
           policy, format, resource):
    """report on a cross account policy execution."""
    accounts_config, custodian_config, executor = init(
        config, use, debug, verbose, accounts, tags, policy, resource=resource)

    resource_types = set()
    for p in custodian_config.get('policies'):
        resource_types.add(p['resource'])
    if len(resource_types) > 1:
        raise ValueError("can only report on one resource type at a time")
    elif not len(custodian_config['policies']) > 0:
        raise ValueError("no matching policies found")

    records = []
    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config.get('accounts', ()):
            for r in resolve_regions(region or a.get('regions', ())):
                futures[w.submit(
                    report_account,
                    a, r,
                    custodian_config,
                    output_dir,
                    debug)] = (a, r)

        for f in as_completed(futures):
            a, r = futures[f]
            if f.exception():
                if debug:
                    raise
                log.warning(
                    "Error running policy in %s @ %s exception: %s",
                    a['name'], r, f.exception())
            records.extend(f.result())

    log.debug(
        "Found %d records across %d accounts and %d policies",
        len(records), len(accounts_config['accounts']),
        len(custodian_config['policies']))

    if format == 'json':
        dumps(records, output, indent=2)
        return

    prefix_fields = OrderedDict(
        (('Account', 'account'), ('Region', 'region'), ('Policy', 'policy')))
    config = Config.empty()
    factory = resource_registry.get(list(resource_types)[0])

    formatter = Formatter(
        factory.resource_type,
        extra_fields=field,
        include_default_fields=not(no_default_fields),
        include_region=False,
        include_policy=False,
        fields=prefix_fields)

    rows = formatter.to_csv(records, unique=False)
    writer = UnicodeWriter(output, formatter.headers())
    writer.writerow(formatter.headers())
    writer.writerows(rows)


def run_account_script(account, region, output_dir, debug, script_args):
    try:
        session = get_session(account, "org-script", region)
        creds = session._session.get_credentials()
    except ClientError:
        log.error(
            "unable to obtain credentials for account:%s role:%s",
            account['name'], account['role'])
        return 1

    env = os.environ.copy()
    env['AWS_ACCESS_KEY_ID'] = creds.access_key
    env['AWS_SECRET_ACCESS_KEY'] = creds.secret_key
    env['AWS_SESSION_TOKEN'] = creds.token
    env['AWS_DEFAULT_REGION'] = region

    log.info("running script on account:%s region:%s script: `%s`",
             account['name'], region, " ".join(script_args))

    if debug:
        subprocess.check_call(args=script_args, env=env)
        return 0

    output_dir = os.path.join(output_dir, account['name'], region)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(os.path.join(output_dir, 'stdout'), 'wb') as stdout:
        with open(os.path.join(output_dir, 'stderr'), 'wb') as stderr:
            return subprocess.call(
                args=script_args, env=env, stdout=stdout, stderr=stderr)


@cli.command(name='run-script', context_settings=dict(ignore_unknown_options=True))
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option('-s', '--output-dir', required=True, type=click.Path())
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('-r', '--region', default=None, multiple=True)
@click.option('--echo', default=False, is_flag=True)
@click.option('--serial', default=False, is_flag=True)
@click.argument('script_args', nargs=-1, type=click.UNPROCESSED)
def run_script(config, output_dir, accounts, tags, region, echo, serial, script_args):
    """run an aws script across accounts"""
    # TODO count up on success / error / error list by account
    accounts_config, custodian_config, executor = init(
        config, None, serial, True, accounts, tags, ())

    if echo:
        print("command to run: `%s`" % (" ".join(script_args)))
        return

    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config.get('accounts', ()):
            for r in resolve_regions(region or a.get('regions', ())):
                futures[
                    w.submit(run_account_script, a, r, output_dir,
                             serial, script_args)] = (a, r)
        for f in as_completed(futures):
            a, r = futures[f]
            if f.exception():
                if serial:
                    raise
                log.warning(
                    "Error running script in %s @ %s exception: %s",
                    a['name'], r, f.exception())
            exit_code = f.result()
            if exit_code == 0:
                log.info(
                    "ran script on account:%s region:%s script: `%s`",
                    a['name'], r, " ".join(script_args))
            else:
                log.info(
                    "error running script on account:%s region:%s script: `%s`",
                    a['name'], r, " ".join(script_args))


def run_account(account, region, policies_config, output_path,
                cache_period, metrics, dryrun, debug):
    """Execute a set of policies on an account.
    """
    logging.getLogger('custodian.output').setLevel(logging.ERROR + 1)
    CONN_CACHE.session = None
    CONN_CACHE.time = None
    output_path = os.path.join(output_path, account['name'], region)
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    cache_path = os.path.join(output_path, "c7n.cache")
    config = Config.empty(
        region=region,
        cache_period=cache_period, dryrun=dryrun, output_dir=output_path,
        account_id=account['account_id'], metrics_enabled=metrics,
        cache=cache_path, log_group=None, profile=None, external_id=None)

    if account.get('role'):
        config['assume_role'] = account['role']
        config['external_id'] = account.get('external_id')
    elif account.get('profile'):
        config['profile'] = account['profile']

    policies = PolicyCollection.from_data(policies_config, config)
    policy_counts = {}
    st = time.time()
    with environ(**account_tags(account)):
        for p in policies:
            log.debug(
                "Running policy:%s account:%s region:%s",
                p.name, account['name'], region)
            try:
                resources = p.run()
                policy_counts[p.name] = resources and len(resources) or 0
                if not resources:
                    continue
                log.info(
                    "Ran account:%s region:%s policy:%s matched:%d time:%0.2f",
                    account['name'], region, p.name, len(resources),
                    time.time() - st)
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    log.warning('Access denied account:%s region:%s',
                                account['name'], region)
                    return policy_counts
                log.error(
                    "Exception running policy:%s account:%s region:%s error:%s",
                    p.name, account['name'], region, e)
                continue
            except Exception as e:
                log.error(
                    "Exception running policy:%s account:%s region:%s error:%s",
                    p.name, account['name'], region, e)
                if not debug:
                    continue
                import traceback, pdb, sys
                traceback.print_exc()
                pdb.post_mortem(sys.exc_info()[-1])
                raise

    return policy_counts


@cli.command(name='run')
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option("-u", "--use", required=True)
@click.option('-s', '--output-dir', required=True, type=click.Path())
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('-r', '--region', default=None, multiple=True)
@click.option('-p', '--policy', multiple=True)
@click.option('--cache-period', default=15, type=int)
@click.option("--metrics", default=False, is_flag=True)
@click.option("--dryrun", default=False, is_flag=True)
@click.option('--debug', default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
def run(config, use, output_dir, accounts, tags,
        region, policy, cache_period, metrics, dryrun, debug, verbose):
    """run a custodian policy across accounts"""
    accounts_config, custodian_config, executor = init(
        config, use, debug, verbose, accounts, tags, policy)
    policy_counts = Counter()
    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config.get('accounts', ()):
            for r in resolve_regions(region or a.get('regions', ())):
                futures[w.submit(
                    run_account,
                    a, r,
                    custodian_config,
                    output_dir,
                    cache_period,
                    metrics,
                    dryrun,
                    debug)] = (a, r)

        for f in as_completed(futures):
            a, r = futures[f]
            if f.exception():
                if debug:
                    raise
                log.warning(
                    "Error running policy in %s @ %s exception: %s",
                    a['name'], r, f.exception())

            for p, count in f.result().items():
                policy_counts[p] += count

    log.info("Policy resource counts %s" % policy_counts)
