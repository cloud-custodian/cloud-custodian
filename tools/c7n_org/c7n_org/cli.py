# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Run a custodian policy across an organization's accounts
"""

import csv
from collections import Counter
import logging
import os
import time
import subprocess
import sys

import multiprocessing
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed)
import yaml

from botocore.compat import OrderedDict
from botocore.exceptions import ClientError
import click
import jsonschema

from c7n.credentials import assumed_session, SessionFactory
from c7n.executor import MainThreadExecutor
from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.provider import get_resource_class
from c7n.reports.csvout import Formatter, fs_record_set
from c7n.resources import load_available
from c7n.utils import CONN_CACHE, dumps

from c7n_org.utils import environ, account_tags

log = logging.getLogger('c7n_org')

# Workaround OSX issue, note this exists for py2 but there
# isn't anything we can do in that case.
# https://bugs.python.org/issue33725
if sys.platform == 'darwin' and (
        sys.version_info.major > 3 and sys.version_info.minor > 4):
    multiprocessing.set_start_method('spawn')


WORKER_COUNT = int(
    os.environ.get('C7N_ORG_PARALLEL', multiprocessing.cpu_count() * 4))


CONFIG_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema',
    'id': 'http://schema.cloudcustodian.io/v0/orgrunner.json',
    'definitions': {
        'account': {
            'type': 'object',
            'additionalProperties': True,
            'anyOf': [
                {'required': ['role', 'account_id']},
                {'required': ['profile', 'account_id']}
            ],
            'properties': {
                'name': {'type': 'string'},
                'email': {'type': 'string'},
                'account_id': {
                    'type': 'string',
                    'pattern': '^[0-9]{12}$',
                    'minLength': 12, 'maxLength': 12},
                'profile': {'type': 'string', 'minLength': 3},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'regions': {'type': 'array', 'items': {'type': 'string'}},
                'role': {'oneOf': [
                    {'type': 'array', 'items': {'type': 'string'}},
                    {'type': 'string', 'minLength': 3}]},
                'external_id': {'type': 'string'},
                'vars': {'type': 'object'},
            }
        },
        'subscription': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['subscription_id'],
            'properties': {
                'subscription_id': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'name': {'type': 'string'},
                'vars': {'type': 'object'},
            }
        },
        'project': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['project_id'],
            'properties': {
                'project_id': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'name': {'type': 'string'},
                'vars': {'type': 'object'},
            }
        },
    },
    'type': 'object',
    'additionalProperties': False,
    'oneOf': [
        {'required': ['accounts']},
        {'required': ['projects']},
        {'required': ['subscriptions']}
    ],
    'properties': {
        'vars': {'type': 'object'},
        'accounts': {
            'type': 'array',
            'items': {'$ref': '#/definitions/account'}
        },
        'subscriptions': {
            'type': 'array',
            'items': {'$ref': '#/definitions/subscription'}
        },
        'projects': {
            'type': 'array',
            'items': {'$ref': '#/definitions/project'}
        }
    }
}


@click.group()
def cli():
    """custodian organization multi-account runner."""


class LogFilter:
    """We want to keep the main c7n-org cli output to be readable.

    We previously did so via squelching custodian's log output via
    level filter on the logger, however doing that meant that log
    outputs stored to output locations were also squelched.

    We effectively want differential handling at the top level logger
    stream handler, ie. we want `custodian` log messages to propagate
    to the root logger based on level, but we also want them to go the
    custodian logger's directly attached handlers on debug level.
    """

    def filter(self, r):
        if not r.name.startswith('custodian'):
            return 1
        elif r.levelno >= logging.WARNING:
            return 1
        return 0


def init(config, use, debug, verbose, accounts, tags, policies, resource=None, policy_tags=()):
    level = verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")

    logging.getLogger().setLevel(level)
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    logging.getLogger('custodian.s3').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    # Filter out custodian log messages on console output if not
    # at warning level or higher, see LogFilter docs and #2674
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler):
            h.addFilter(LogFilter())

    with open(config, 'rb') as fh:
        accounts_config = yaml.safe_load(fh.read())
        jsonschema.validate(accounts_config, CONFIG_SCHEMA)

    if use:
        with open(use) as fh:
            custodian_config = yaml.safe_load(fh.read())
    else:
        custodian_config = {}

    accounts_config['accounts'] = list(accounts_iterator(accounts_config))
    filter_policies(custodian_config, policy_tags, policies, resource)
    filter_accounts(accounts_config, tags, accounts)

    load_available()
    MainThreadExecutor.c7n_async = False
    executor = debug and MainThreadExecutor or ProcessPoolExecutor
    return accounts_config, custodian_config, executor


def resolve_regions(regions, account):
    if 'all' in regions:
        session = get_session(account, 'c7n-org', "us-east-1")
        client = session.client('ec2')
        return [region['RegionName'] for region in client.describe_regions()['Regions']]
    if not regions:
        return ('us-east-1', 'us-west-2')
    return regions


def get_session(account, session_name, region):
    if account.get('provider') != 'aws':
        return None
    if account.get('role'):
        roles = account['role']
        if isinstance(roles, str):
            roles = [roles]
        s = None
        for r in roles:
            try:
                s = assumed_session(
                    r, session_name, region=region,
                    external_id=account.get('external_id'),
                    session=s)
            except ClientError as e:
                log.error(
                    "unable to obtain credentials for account:%s role:%s error:%s",
                    account['name'], r, e)
                raise
        return s
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
        account_id = a.get('account_id') or a.get('project_id') or a.get('subscription_id') or ''
        if accounts and a['name'] not in accounts and account_id not in accounts:
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


def filter_policies(policies_config, tags, policies, resource, not_policies=None):
    filtered_policies = []
    for p in policies_config.get('policies', ()):
        if not_policies and p['name'] in not_policies:
            continue
        if policies and p['name'] not in policies:
            continue
        if resource and p['resource'] != resource:
            continue
        if tags:
            found = set()
            for t in tags:
                if t in p.get('tags', ()):
                    found.add(t)
            if not found == set(tags):
                continue
        filtered_policies.append(p)
    policies_config['policies'] = filtered_policies


def report_account(account, region, policies_config, output_path, cache_path, debug):
    output_path = os.path.join(output_path, account['name'], region)
    cache_path = os.path.join(cache_path, "%s-%s.cache" % (account['name'], region))

    load_available()
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
        # initializee policy execution context for output access
        p.ctx.initialize()
        log.debug(
            "Report policy:%s account:%s region:%s path:%s",
            p.name, account['name'], region, output_path)
        policy_records = fs_record_set(p.ctx.log_dir, p.name)
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
@click.option('-t', '--tags', multiple=True, default=None, help="Account tag filter")
@click.option('-r', '--region', default=None, multiple=True)
@click.option('--debug', default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('-p', '--policy', multiple=True)
@click.option('-l', '--policytags', 'policy_tags',
              multiple=True, default=None, help="Policy tag filter")
@click.option('--format', default='csv', type=click.Choice(['csv', 'json']))
@click.option('--resource', default=None)
@click.option('--cache-path', required=False, type=click.Path(), default="~/.cache/c7n-org")
def report(config, output, use, output_dir, accounts,
           field, no_default_fields, tags, region, debug, verbose,
           policy, policy_tags, format, resource, cache_path):
    """report on a cross account policy execution."""
    accounts_config, custodian_config, executor = init(
        config, use, debug, verbose, accounts, tags, policy,
        resource=resource, policy_tags=policy_tags)

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
            for r in resolve_regions(region or a.get('regions', ()), a):
                futures[w.submit(
                    report_account,
                    a, r,
                    custodian_config,
                    output_dir,
                    cache_path,
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

    factory = get_resource_class(list(resource_types)[0])
    formatter = Formatter(
        factory.resource_type,
        extra_fields=field,
        include_default_fields=not(no_default_fields),
        include_region=False,
        include_policy=False,
        fields=prefix_fields)

    rows = formatter.to_csv(records, unique=False)
    writer = csv.writer(output, formatter.headers())
    writer.writerow(formatter.headers())
    writer.writerows(rows)


def _get_env_creds(account, session, region):
    env = {}
    if account["provider"] == 'aws':
        creds = session._session.get_credentials()
        env['AWS_ACCESS_KEY_ID'] = creds.access_key
        env['AWS_SECRET_ACCESS_KEY'] = creds.secret_key
        env['AWS_SESSION_TOKEN'] = creds.token
        env['AWS_DEFAULT_REGION'] = region
        env['AWS_ACCOUNT_ID'] = account["account_id"]
    elif account["provider"] == 'azure':
        env['AZURE_SUBSCRIPTION_ID'] = account["account_id"]
    elif account["provider"] == 'gcp':
        env['GOOGLE_CLOUD_PROJECT'] = account["account_id"]
        env['CLOUDSDK_CORE_PROJECT'] = account["account_id"]
    return env


def run_account_script(account, region, output_dir, debug, script_args):

    try:
        session = get_session(account, "org-script", region)
    except ClientError:
        return 1

    env = os.environ.copy()
    env.update(_get_env_creds(account, session, region))

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
@click.option('-t', '--tags', multiple=True, default=None, help="Account tag filter")
@click.option('-r', '--region', default=None, multiple=True)
@click.option('--echo', default=False, is_flag=True)
@click.option('--serial', default=False, is_flag=True)
@click.argument('script_args', nargs=-1, type=click.UNPROCESSED)
def run_script(config, output_dir, accounts, tags, region, echo, serial, script_args):
    """run an aws/azure/gcp script across accounts"""
    # TODO count up on success / error / error list by account
    accounts_config, custodian_config, executor = init(
        config, None, serial, True, accounts, tags, (), ())
    if echo:
        print("command to run: `%s`" % (" ".join(script_args)))
        return
    # Support fully quoted scripts, which are common to avoid parameter
    # overlap with c7n-org run-script.
    if len(script_args) == 1 and " " in script_args[0]:
        script_args = script_args[0].split()

    success = True

    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config.get('accounts', ()):
            for r in resolve_regions(region or a.get('regions', ()), a):
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
                success = False
            exit_code = f.result()
            if exit_code == 0:
                log.info(
                    "ran script on account:%s region:%s script: `%s`",
                    a['name'], r, " ".join(script_args))
            else:
                log.info(
                    "error running script on account:%s region:%s script: `%s`",
                    a['name'], r, " ".join(script_args))
                success = False

    if not success:
        sys.exit(1)


def accounts_iterator(config):
    for a in config.get('accounts', ()):
        if 'role' in a:
            if isinstance(a['role'], str) and not a['role'].startswith('arn'):
                a['role'] = "arn:aws:iam::{}:role/{}".format(
                    a['account_id'], a['role'])
        yield {**a, **{'provider': 'aws'}}
    for a in config.get('subscriptions', ()):
        d = {'account_id': a['subscription_id'],
             'name': a.get('name', a['subscription_id']),
             'regions': ['global'],
             'provider': 'azure',
             'tags': a.get('tags', ()),
             'vars': a.get('vars', {})}
        yield d
    for a in config.get('projects', ()):
        d = {'account_id': a['project_id'],
             'name': a.get('name', a['project_id']),
             'regions': ['global'],
             'provider': 'gcp',
             'tags': a.get('tags', ()),
             'vars': a.get('vars', {})}
        yield d


def run_account(account, region, policies_config, output_path,
                cache_period, cache_path, metrics, dryrun, debug):
    """Execute a set of policies on an account.
    """
    logging.getLogger('custodian.output').setLevel(logging.ERROR + 1)
    CONN_CACHE.session = None
    CONN_CACHE.time = None
    load_available()

    # allow users to specify interpolated output paths
    if '{' not in output_path:
        output_path = os.path.join(output_path, account['name'], region)

    cache_path = os.path.join(cache_path, "%s-%s.cache" % (account['account_id'], region))

    config = Config.empty(
        region=region, cache=cache_path,
        cache_period=cache_period, dryrun=dryrun, output_dir=output_path,
        account_id=account['account_id'], metrics_enabled=metrics,
        log_group=None, profile=None, external_id=None)

    env_vars = account_tags(account)

    if account.get('role'):
        if isinstance(account['role'], str):
            config['assume_role'] = account['role']
            config['external_id'] = account.get('external_id')
        else:
            env_vars.update(
                _get_env_creds(account, get_session(account, 'custodian', region), region))

    elif account.get('profile'):
        config['profile'] = account['profile']

    policies = PolicyCollection.from_data(policies_config, config)
    policy_counts = {}
    success = True
    st = time.time()

    with environ(**env_vars):
        for p in policies:
            # Extend policy execution conditions with account information
            p.conditions.env_vars['account'] = account
            # Variable expansion and non schema validation (not optional)
            p.expand_variables(p.get_variables(account.get('vars', {})))
            p.validate()
            log.debug(
                "Running policy:%s account:%s region:%s",
                p.name, account['name'], region)
            try:
                resources = p.run()
                policy_counts[p.name] = resources and len(resources) or 0
                if not resources:
                    continue
                if not config.dryrun and p.execution_mode != 'pull':
                    log.info("Ran account:%s region:%s policy:%s provisioned time:%0.2f",
                             account['name'], region, p.name, time.time() - st)
                    continue
                log.info(
                    "Ran account:%s region:%s policy:%s matched:%d time:%0.2f",
                    account['name'], region, p.name, len(resources),
                    time.time() - st)
            except ClientError as e:
                success = False
                if e.response['Error']['Code'] == 'AccessDenied':
                    log.warning('Access denied api:%s policy:%s account:%s region:%s',
                                e.operation_name, p.name, account['name'], region)
                    return policy_counts, success
                log.error(
                    "Exception running policy:%s account:%s region:%s error:%s",
                    p.name, account['name'], region, e)
                continue
            except Exception as e:
                success = False
                log.error(
                    "Exception running policy:%s account:%s region:%s error:%s",
                    p.name, account['name'], region, e)
                if not debug:
                    continue
                import traceback, pdb, sys
                traceback.print_exc()
                pdb.post_mortem(sys.exc_info()[-1])
                raise

    return policy_counts, success


@cli.command(name='run')
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option("-u", "--use", required=True)
@click.option('-s', '--output-dir', required=True, type=click.Path())
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('-t', '--tags', multiple=True, default=None, help="Account tag filter")
@click.option('-r', '--region', default=None, multiple=True)
@click.option('-p', '--policy', multiple=True)
@click.option('-l', '--policytags', 'policy_tags',
              multiple=True, default=None, help="Policy tag filter")
@click.option('--cache-period', default=15, type=int)
@click.option('--cache-path', required=False,
              type=click.Path(
                  writable=True, readable=True, exists=True,
                  resolve_path=True, allow_dash=False,
                  file_okay=False, dir_okay=True),
              default=None)
@click.option("--metrics", default=False, is_flag=True)
@click.option("--metrics-uri", default=None, help="Configure provider metrics target")
@click.option("--dryrun", default=False, is_flag=True)
@click.option('--debug', default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
def run(config, use, output_dir, accounts, tags, region,
        policy, policy_tags, cache_period, cache_path, metrics,
        dryrun, debug, verbose, metrics_uri):
    """run a custodian policy across accounts"""
    accounts_config, custodian_config, executor = init(
        config, use, debug, verbose, accounts, tags, policy, policy_tags=policy_tags)
    policy_counts = Counter()
    success = True

    if metrics_uri:
        metrics = metrics_uri

    if not cache_path:
        cache_path = os.path.expanduser("~/.cache/c7n-org")
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)

    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config['accounts']:
            for r in resolve_regions(region or a.get('regions', ()), a):
                futures[w.submit(
                    run_account,
                    a, r,
                    custodian_config,
                    output_dir,
                    cache_period,
                    cache_path,
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
                continue

            account_region_pcounts, account_region_success = f.result()
            for p in account_region_pcounts:
                policy_counts[p] += account_region_pcounts[p]

            if not account_region_success:
                success = False

    log.info("Policy resource counts %s" % policy_counts)

    if not success:
        sys.exit(1)
