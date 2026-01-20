# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Run a custodian policy across an organization's accounts
"""

import csv
from collections import Counter
from datetime import timedelta, datetime
import logging
import os
import time
import subprocess  # nosec
import sys
import shlex
import re
import copy

import multiprocessing
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed)
import yaml

from botocore.compat import OrderedDict
from botocore.exceptions import ClientError
import click
import jsonschema

from c7n import schema, deprecated
from c7n.credentials import assumed_session, SessionFactory
from c7n.executor import MainThreadExecutor
from c7n.exceptions import InvalidOutputConfig
from c7n.config import Config, Bag
from c7n.loader import SourceLocator
from c7n.policy import PolicyCollection, Policy, PolicyValidationError
from c7n.provider import get_resource_class, clouds as cloud_providers
from c7n.reports.csvout import Formatter, fs_record_set, record_set, strip_output_path
from c7n.resources import load_available, load_resources
from c7n.schema import StructureParser
from c7n.utils import (
    CONN_CACHE, dumps, filter_empty, format_string_values, get_policy_provider, join_output_path)

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
                'display_name': {'type': 'string'},
                'org_id': {'type': 'string'},
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
                'region': {'type': 'string'},
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
        'tenancy': {
            'type': 'object',
            'additionalProperties': True,
            'required': ['profile'],
            'properties': {
                'name': {'type': 'string'},
                'profile': {'type': 'string', 'minLength': 2},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
                'regions': {'type': 'array', 'items': {'type': 'string'}},
                'vars': {'type': 'object'},
                }
            }
        },
    'type': 'object',
    'additionalProperties': False,
    'oneOf': [
        {'required': ['accounts']},
        {'required': ['projects']},
        {'required': ['subscriptions']},
        {'required': ['tenancies']}
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
        },
        'tenancies': {
            'type': 'array',
            'items': {'$ref': '#/definitions/tenancy'}
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


def init(config, use, debug, verbose, accounts, tags, policies,
        resource=None, policy_tags=(), not_accounts=None):
    level = verbose and logging.DEBUG or logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s")

    logging.getLogger().setLevel(level)
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    logging.getLogger('custodian.s3').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    accounts = comma_expand(accounts)
    policies = comma_expand(policies)
    tags = comma_expand(tags)
    policy_tags = comma_expand(policy_tags)

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
    filter_accounts(accounts_config, tags, accounts, not_accounts)

    load_available()
    MainThreadExecutor.c7n_async = False
    executor = debug and MainThreadExecutor or ProcessPoolExecutor
    return accounts_config, custodian_config, executor


def resolve_regions(regions, account):
    if 'all' in regions:
        try:
            session = get_session(account, 'c7n-org', 'us-east-1')
            client = session.client('ec2')
            return [region['RegionName'] for region in client.describe_regions()['Regions']]
        except ClientError as e:
            err = e.response['Error']
            if err['Code'] not in ('AccessDenied', 'AuthFailure'):
                raise
            log.warning('error (%s) listing available regions for account:%s - %s',
                err['Code'], account['name'], err['Message']
            )
            return []
    if not regions:
        return ('us-east-1', 'us-west-2')

    return comma_expand(regions)


def comma_expand(values):
    resolved_values = []
    if not values:
        return []
    for v in values:
        if ',' in v:
            resolved_values.extend([n.strip() for n in v.split(',')])
        elif v:
            resolved_values.append(v)
    # unique the set
    return list(dict.fromkeys(resolved_values))


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
    accounts = comma_expand(accounts)
    not_accounts = comma_expand(not_accounts)
    for a in accounts_config.get('accounts', ()):
        # NOTE only "account_id" would be available since the account conf has been normalized
        account_id = a.get('account_id') or ''
        if not_accounts and (a['name'] in not_accounts or account_id in not_accounts):
            continue
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

        if p.ctx.output.type == "s3":
            delta = timedelta(days=1)
            begin_date = datetime.now() - delta

            policy_records = record_set(
                p.session_factory,
                p.ctx.output.config['netloc'],
                strip_output_path(p.ctx.output.config['path'], p.name),
                begin_date
            )
        else:
            policy_records = fs_record_set(p.ctx.log_dir, p.name)

        for r in policy_records:
            r['policy'] = p.name
            r['region'] = p.options.region
            r['account'] = account['name']
            r['account_id'] = account.get('account_id', '')
            for t in account.get('tags', ()):
                if ':' in t:
                    k, v = t.split(':', 1)
                    if k in r:
                        k = 'tag:' + k
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
        include_default_fields=not no_default_fields,
        include_region=False,
        include_policy=False,
        fields=prefix_fields)

    rows = formatter.to_csv(records, unique=False)
    writer = csv.writer(output, formatter.headers(), quoting=csv.QUOTE_ALL)
    writer.writerow(formatter.headers())
    writer.writerows(rows)


def validate_basic(custodian_config, policy_file, fmt, check_mode, verbose):
    """Run basic account-agnostic validation (Phase 1 logic).

    Args:
        custodian_config: Parsed policy configuration
        policy_file: Path to policy file (for error reporting)
        fmt: File format ('yml', 'yaml', 'json')
        check_mode: Deprecation check mode (deprecated.SKIP, deprecated.STRICT, or None)
        verbose: Verbose logging flag

    Returns:
        bool: True if validation passes, False otherwise
    """

    # Core validation logic
    structure = StructureParser()
    errors = []
    used_policy_names = set()
    found_deprecations = False
    footnotes = deprecated.Footnotes()

    # Structure validation
    log.debug("Running structure validation")
    try:
        structure.validate(custodian_config)
    except PolicyValidationError as e:
        log.error(f"Configuration invalid: {policy_file}")
        log.error(str(e))
        return False

    # Load resources for schema validation
    log.debug("Loading resources for schema validation")
    resource_types = structure.get_resource_types(custodian_config)
    log.debug(f"Resource types found: {resource_types}")
    load_resources(resource_types)

    # Schema validation
    log.debug("Running schema validation")
    schm = schema.generate()
    errors = schema.validate(custodian_config, schm)

    # Check for duplicate policy names
    log.debug("Checking for duplicate policy names")
    conf_policy_names = {
        p.get('name', 'unknown') for p in custodian_config.get('policies', ())}
    dupes = conf_policy_names.intersection(used_policy_names)
    if len(dupes) >= 1:
        errors.append(ValueError(
            f"Only one policy with a given name allowed, duplicates: {', '.join(dupes)}"
        ))
    used_policy_names = used_policy_names.union(conf_policy_names)

    # Policy-level validation
    if not errors:
        log.debug("Running policy-level validation")
        null_config = Config.empty(dryrun=True, account_id='na', region='na')
        source_locator = None
        if fmt in ('yml', 'yaml'):
            source_locator = SourceLocator(policy_file)

        for p in custodian_config.get('policies', ()):
            policy_name = p.get('name', 'unknown')
            log.debug(f"Validating policy: {policy_name}")
            try:
                policy = Policy(p, null_config, Bag())
                policy.validate()

                # Check deprecations
                if check_mode != deprecated.SKIP:
                    report = deprecated.report(policy)
                    if report:
                        found_deprecations = True
                        log.warning(
                            "deprecated usage found in policy\n" +
                            report.format(
                                source_locator=source_locator,
                                footnotes=footnotes))
            except Exception as e:
                msg = f"Policy: {policy_name} is invalid: {e}"
                errors.append(msg)

    # Report results
    if errors:
        log.error(f"Configuration invalid: {policy_file}")
        for e in errors:
            log.error(str(e))
        return False

    log.info(f"Configuration valid: {policy_file}")

    # Handle deprecations
    if found_deprecations:
        notes = footnotes()
        if notes:
            log.warning("deprecation footnotes:\n" + notes)
        if check_mode == deprecated.STRICT:
            log.error("Deprecations found with --check-deprecations=strict")
            return False

    log.info("Validation complete - all policies are valid!")
    return True


def find_unexpanded_variables(obj, path="", allowed_placeholders=None):
    """Recursively find unexpanded variable references in policy data.

    This function identifies variable placeholders (e.g., {variable_name}) that remain
    unexpanded in policy data. Framework runtime variables can be explicitly allowed
    by passing them in the allowed_placeholders parameter.

    Args:
        obj: Policy data object (dict, list, str, or other)
        path: Current path in the object tree (for error reporting)
        allowed_placeholders: Optional set of placeholder strings (e.g., {'{event}', '{op}'})
                              that should NOT be flagged as errors. These represent framework
                              runtime variables that are intentionally not expanded during
                              validation. If None (default), no placeholders are allowed.

    Returns:
        list: List of tuples (path, unexpanded_string) for each unexpanded variable
              that is not in the allowed_placeholders set

    Example:
        # Flag all unexpanded variables (default behavior)
        errors = find_unexpanded_variables(policy_data)

        # Allow framework runtime variables
        framework_vars = extract_framework_runtime_variables(variables)
        errors = find_unexpanded_variables(policy_data, allowed_placeholders=framework_vars)
    """
    unexpanded = []
    var_pattern = re.compile(r'\{[^}]+\}')

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            unexpanded.extend(find_unexpanded_variables(value, new_path, allowed_placeholders))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            new_path = f"{path}[{idx}]"
            unexpanded.extend(find_unexpanded_variables(item, new_path, allowed_placeholders))
    elif isinstance(obj, str):
        # Check if string contains variable placeholders
        if var_pattern.search(obj):
            # Extract variable names from the string
            matches = var_pattern.findall(obj)
            for match in matches:
                # Skip framework runtime variables that are intentionally not expanded
                if allowed_placeholders and match in allowed_placeholders:
                    continue
                unexpanded.append((path, match))

    return unexpanded


def extract_framework_runtime_variables(variables):
    """Extract framework runtime variables that should remain unexpanded.

    Cloud Custodian's Policy.get_variables() returns a dict where some values
    are placeholder strings like '{event}', '{op}', etc. These are intentionally
    NOT expanded during validation because they're only available at runtime.

    This function identifies those placeholders by looking for string values
    that match the pattern {variable_name}. This approach is provider-agnostic
    and works across AWS, Azure, and GCP by querying the actual Policy object's
    variable definitions rather than using hardcoded lists.

    Args:
        variables: Dictionary returned by Policy.get_variables()

    Returns:
        set: Set of placeholder strings like '{event}', '{op}', etc.

    Example:
        variables = {
            'account_id': '123456789012',  # Expanded value
            'region': 'us-east-1',         # Expanded value
            'event': '{event}',            # Runtime placeholder
            'op': '{op}'                   # Runtime placeholder
        }
        Returns: {'{event}', '{op}'}
    """
    runtime_placeholders = set()
    # Match strings that are EXACTLY a placeholder: {something}
    # This excludes partial matches like "arn:aws:iam::{account_id}::role/name"
    placeholder_pattern = re.compile(r'^\{[^}]+\}$')

    for key, value in variables.items():
        # Only consider string values that match the exact placeholder pattern
        if isinstance(value, str) and placeholder_pattern.match(value):
            runtime_placeholders.add(value)

    return runtime_placeholders


def validate_per_account(custodian_config, accounts_config, policy_file,
                        fmt, check_mode, verbose):
    """Run per-account validation with variable expansion.

    Validates policies for each account, expanding account-specific variables
    and checking for missing or invalid variable references.

    This function validates that policies work correctly with each account's
    specific configuration and variables. It handles multi-cloud scenarios by
    matching policy providers with account providers.

    Args:
        custodian_config: Parsed policy configuration
        accounts_config: Parsed account configuration
        policy_file: Path to policy file (for error reporting)
        fmt: File format ('yml', 'yaml', 'json')
        check_mode: Deprecation check mode
        verbose: Verbose logging flag

    Returns:
        bool: True if validation passes for all accounts, False otherwise
    """
    accounts = accounts_config['accounts']
    policies = custodian_config.get('policies', [])

    log.info(f"Validating {len(policies)} policies across {len(accounts)} accounts")

    # First, run basic validation to catch structural issues
    log.debug("Running initial basic validation")
    if not validate_basic(custodian_config, policy_file, fmt, check_mode, verbose):
        return False

    # Track results per account
    account_results = {}
    overall_success = True

    # Validate for each account
    for account in accounts:
        account_name = account.get('name', account.get('account_id', 'unknown'))
        log.info(f"Validating for account: {account_name}")

        account_errors = []
        account_warnings = []

        # Get account-specific variables
        account_vars = account.get('vars', {})
        if verbose and account_vars:
            log.debug(f"  Account variables: {list(account_vars.keys())}")

        # Get account info (already normalized by accounts_iterator)
        account_id = account.get('account_id', 'na')
        account_provider = account.get('provider', 'aws')

        # Use region from account config
        # accounts_iterator() has already set appropriate region defaults per provider
        regions = account.get('regions', ['na'])
        region = regions[0] if regions else 'na'

        if verbose:
            log.debug(f"  Account provider: {account_provider}, region: {region}")

        # Create config for this account
        account_config = Config.empty(
            dryrun=True,
            account_id=account_id,
            region=region
        )

        source_locator = None
        if fmt.lower() in ('yml', 'yaml'):
            source_locator = SourceLocator(policy_file)

        # Validate each policy with account context
        for policy_data in policies:
            policy_name = policy_data.get('name', 'unknown')

            # Determine policy provider from resource type
            resource_type = policy_data.get('resource', '')
            if '.' in resource_type:
                policy_provider = resource_type.split('.')[0]
            else:
                # Default to aws for unqualified resource types
                policy_provider = 'aws'

            # Skip if policy provider doesn't match account provider
            if policy_provider != account_provider:
                if verbose:
                    log.debug(
                        f"  Skipping policy '{policy_name}' for account '{account_name}' "
                        f"(provider mismatch: policy={policy_provider}, "
                        f"account={account_provider})"
                    )
                continue

            if verbose:
                log.debug(f"  Validating policy: {policy_name}")

            try:
                # Make a deep copy to avoid modifying original
                policy_data_copy = copy.deepcopy(policy_data)

                # Create policy object
                policy = Policy(policy_data_copy, account_config, Bag())

                # Get variables (this adds runtime variables)
                variables = policy.get_variables(account_vars)

                # Extract framework runtime variables BEFORE expansion
                # These are placeholders like {event}, {op} that remain unexpanded
                # because they're only available at policy execution time, not validation time
                framework_runtime_vars = extract_framework_runtime_variables(variables)

                # Expand variables (modifies policy.data in place)
                # This expands user-defined variables from account config
                policy.expand_variables(variables)

                # Check for unexpanded variables, but allow framework runtime placeholders
                # User-defined variables that couldn't be resolved will still be flagged
                unexpanded = find_unexpanded_variables(
                    policy.data,
                    f"policy.{policy_name}",
                    allowed_placeholders=framework_runtime_vars
                )
                if unexpanded:
                    for path, var in unexpanded:
                        var_name = var.strip('{}')
                        msg = (f"Policy '{policy_name}' references undefined "
                               f"variable '{var_name}' at {path}")
                        account_errors.append(msg)
                    continue

                # Validate expanded policy
                try:
                    policy.validate()
                except Exception as e:
                    msg = f"Policy '{policy_name}' validation failed after variable expansion: {e}"
                    account_errors.append(msg)
                    continue

                # Check deprecations
                if check_mode != deprecated.SKIP:
                    report = deprecated.report(policy)
                    if report:
                        warning = f"Policy '{policy_name}' uses deprecated features"
                        account_warnings.append(warning)
                        if verbose:
                            log.warning(f"  {warning}\n" +
                                      report.format(source_locator=source_locator))

            except Exception as e:
                msg = f"Policy '{policy_name}' unexpected error: {e}"
                account_errors.append(msg)

        # Store results for this account
        account_results[account_name] = {
            'errors': account_errors,
            'warnings': account_warnings,
            'success': len(account_errors) == 0
        }

        if not account_results[account_name]['success']:
            overall_success = False

    # Report results
    log.info("=" * 60)
    log.info("Per-Account Validation Summary")
    log.info("=" * 60)

    accounts_with_errors = []
    accounts_with_warnings = []
    accounts_valid = []

    for account_name, result in account_results.items():
        if result['errors']:
            accounts_with_errors.append(account_name)
            log.error(f"Account validation FAILED: {account_name}")
            for error in result['errors']:
                log.error(f"  {error}")
        elif result['warnings']:
            accounts_with_warnings.append(account_name)
            log.warning(f"Account validation PASSED with warnings: {account_name}")
            for warning in result['warnings']:
                log.warning(f"  {warning}")
        else:
            accounts_valid.append(account_name)
            log.info(f"Account validation PASSED: {account_name}")

    # Final summary
    log.info("=" * 60)
    log.info(f"Total Accounts: {len(account_results)}")
    log.info(f"  Valid: {len(accounts_valid)}")
    log.info(f"  With Warnings: {len(accounts_with_warnings)}")
    log.info(f"  With Errors: {len(accounts_with_errors)}")
    log.info("=" * 60)

    if overall_success:
        log.info("All accounts validated successfully")
        # Check if deprecations should fail in strict mode
        if check_mode == deprecated.STRICT and accounts_with_warnings:
            log.error("Deprecations found with --check-deprecations=strict")
            return False
        return True
    else:
        log.error(f"Validation failed for {len(accounts_with_errors)} account(s): "
                  f"{', '.join(accounts_with_errors)}")
        return False


@cli.command()
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option('-u', '--use', required=True, help="Policy config file(s)")
@click.option('-p', '--policy', multiple=True, help="Policy name filter")
@click.option('-l', '--policytags', 'policy_tags',
              multiple=True, default=None, help="Policy tag filter")
@click.option('--resource', default=None, help="Resource type filter")
@click.option('-a', '--accounts', multiple=True, default=None,
              help="Account name or id filter")
@click.option('--tags', multiple=True, default=None,
              help="Account tag filter")
@click.option('--not-accounts', multiple=True, default=None,
              help="Exclude accounts")
@click.option('--per-account', default=False, is_flag=True,
              help="Validate per account with variable expansion")
@click.option('--check-deprecations',
              type=click.Choice(['skip', 'warn', 'strict']),
              default='warn',
              help="Check for deprecated features")
@click.option('--debug', default=False, is_flag=True, help="Enable debug logging")
@click.option('-v', '--verbose', default=False, help="Verbose output", is_flag=True)
def validate(config, use, policy, policy_tags, resource,
             accounts, tags, not_accounts, per_account,
             check_deprecations, debug, verbose):
    """validate policy files for c7n-org execution."""
    # Setup logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s"
    )
    # Suppress noisy third-party loggers
    logging.getLogger('botocore').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('oci').setLevel(logging.ERROR)
    logging.getLogger('oci.circuit_breaker').setLevel(logging.ERROR)

    log.info("Starting policy validation")
    if verbose:
        log.debug(f"Config file: {config}")
        log.debug(f"Policy file: {use}")

    # Import validation utilities from c7n.commands
    from c7n.commands import DuplicateKeyCheckLoader
    from c7n import deprecated
    from c7n.resources import load_available

    # Load available resources
    load_available()

    # Load and validate account config
    log.debug("Loading and validating account config")
    try:
        with open(config, 'rb') as fh:
            accounts_config = yaml.safe_load(fh.read())
    except IOError:
        log.error(f"Account config file not found: {config}")
        sys.exit(1)
    except yaml.YAMLError as e:
        log.error(f"Invalid YAML in account config: {e}")
        sys.exit(1)

    # Validate account config against schema
    log.debug("Validating account config schema")
    try:
        jsonschema.validate(accounts_config, CONFIG_SCHEMA)
    except jsonschema.ValidationError as e:
        log.error(f"Account config validation failed: {e.message}")
        if e.path:
            log.error(f"Path: {' -> '.join(str(p) for p in e.path)}")
        sys.exit(1)

    # Normalize accounts using accounts_iterator
    log.debug("Normalizing account configurations")
    accounts_config['accounts'] = list(accounts_iterator(accounts_config))

    # Apply account filters if provided
    if accounts or tags or not_accounts:
        log.debug(
            f"Applying account filters: accounts={accounts}, "
            f"tags={tags}, not_accounts={not_accounts}"
        )
        filter_accounts(accounts_config, tags, accounts, not_accounts)
        log.info(f"Filtered to {len(accounts_config['accounts'])} accounts")
    else:
        log.info(f"Loaded {len(accounts_config['accounts'])} accounts")

    if len(accounts_config['accounts']) == 0:
        log.warning("No accounts selected after filtering")
        sys.exit(0)

    # Load policy config
    log.debug("Loading policy config")
    use = os.path.expanduser(use)
    if not os.path.exists(use):
        log.error(f"Policy config file not found: {use}")
        sys.exit(1)

    fmt = use.rsplit('.', 1)[-1]
    if fmt not in ('yml', 'yaml', 'json'):
        log.error("The policy file must end in .json, .yml or .yaml.")
        sys.exit(1)

    try:
        with open(use) as fh:
            custodian_config = yaml.load(fh.read(), Loader=DuplicateKeyCheckLoader)  # nosec nosemgrep
    except IOError:
        log.error(f"Policy config file not found: {use}")
        sys.exit(1)
    except yaml.YAMLError as e:
        log.error(f"Invalid YAML in policy config: {e}")
        sys.exit(1)

    # Apply policy filters
    log.debug("Applying policy filters")
    policies = custodian_config.get('policies', [])
    original_count = len(policies)

    if policy:
        log.debug(f"Filtering by policy names: {policy}")
        policies = [p for p in policies if p.get('name') in policy]

    if resource:
        log.debug(f"Filtering by resource type: {resource}")
        policies = [p for p in policies if p.get('resource') == resource]

    if policy_tags:
        log.debug(f"Filtering by policy tags: {policy_tags}")
        policies = [p for p in policies if set(policy_tags).issubset(
            set(p.get('tags', [])))]

    custodian_config['policies'] = policies
    log.info(f"Validating {len(policies)} policies (filtered from {original_count})")

    if len(policies) == 0:
        log.warning("No policies to validate after filtering")
        if policy or resource or policy_tags:
            filters_applied = []
            if policy:
                filters_applied.append(f"policy names: {', '.join(policy)}")
            if resource:
                filters_applied.append(f"resource type: {resource}")
            if policy_tags:
                filters_applied.append(f"policy tags: {', '.join(policy_tags)}")
            log.warning(f"Filters applied: {'; '.join(filters_applied)}")
        sys.exit(0)

    # Determine deprecation check mode
    if check_deprecations == 'skip':
        check_mode = deprecated.SKIP
    elif check_deprecations == 'strict':
        check_mode = deprecated.STRICT
    else:
        check_mode = None  # 'warn' mode - check but don't exit

    # Decide validation mode
    if per_account:
        log.info("Running per-account validation mode")
        success = validate_per_account(
            custodian_config,
            accounts_config,
            use,
            fmt,
            check_mode,
            verbose
        )
    else:
        log.info("Running basic validation mode (account-agnostic)")
        success = validate_basic(custodian_config, use, fmt, check_mode, verbose)

    # Exit based on results
    sys.exit(0 if success else 1)


def _get_env_creds(account, session, region, env=None):
    env = env or {}
    if account["provider"] == 'aws':
        creds = session._session.get_credentials()
        env['AWS_ACCESS_KEY_ID'] = creds.access_key
        env['AWS_SECRET_ACCESS_KEY'] = creds.secret_key
        env['AWS_SESSION_TOKEN'] = creds.token
        env['AWS_DEFAULT_REGION'] = region
        env['AWS_REGION'] = region
        env['AWS_ACCOUNT_ID'] = account["account_id"]
        # we're explicitly setting credential and region configuratio
        env.pop('AWS_PROFILE', None)
    elif account["provider"] == 'azure':
        env['AZURE_SUBSCRIPTION_ID'] = account["account_id"]
    elif account["provider"] == 'gcp':
        env['GOOGLE_CLOUD_PROJECT'] = account["account_id"]
        env['CLOUDSDK_CORE_PROJECT'] = account["account_id"]
    return filter_empty(env)


def run_account_script(account, region, output_dir, debug, script_args):

    try:
        session = get_session(account, "org-script", region)
    except ClientError:
        return 1

    env = _get_env_creds(account, session, region, dict(os.environ))
    log.info("running script on account:%s region:%s script: `%s`",
             account['name'], region, " ".join(script_args))

    if debug:
        subprocess.check_call(args=script_args, env=env)  # nosec
        return 0

    output_dir = os.path.join(output_dir, account['name'], region)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    vars = {"account": account["name"], "account_id": account["account_id"],
        "region": region, "output_dir": output_dir}
    script_args = format_string_values(script_args, **vars)

    with open(os.path.join(output_dir, 'stdout'), 'wb') as stdout:
        with open(os.path.join(output_dir, 'stderr'), 'wb') as stderr:
            return subprocess.call(  # nosec
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
    accounts_config, _, executor = init(
        config, None, serial, True, accounts, tags, (), ())
    if echo:
        print("command to run: `%s`" % (" ".join(script_args)))
        return
    if len(script_args) == 1 and " " in script_args[0]:
        script_args = shlex.split(script_args[0])

    success = True

    if "://" in output_dir:
        raise InvalidOutputConfig('run-script only supports local directory outputs')

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
    # NOTE Normalize the account configuration for multi-cloud environments,
    # ensuring that attributes such as "account_id" are readily available.
    org_vars = config.get("vars", {})
    for a in config.get('accounts', ()):
        if 'role' in a:
            if isinstance(a['role'], str) and not a['role'].startswith('arn'):
                a['role'] = "arn:aws:iam::{}:role/{}".format(
                    a['account_id'], a['role'])
        a['vars'] = _update(a.get('vars', {}), org_vars)
        yield {**a, **{'provider': 'aws'}}
    for a in config.get('subscriptions', ()):
        d = {'account_id': a['subscription_id'],
             'name': a.get('name', a['subscription_id']),
             'regions': [a.get('region', 'global')],
             'provider': 'azure',
             'tags': a.get('tags', ()),
             'vars': _update(a.get('vars', {}), org_vars)}
        yield d
    for a in config.get('projects', ()):
        d = {'account_id': a['project_id'],
             'name': a.get('name', a['project_id']),
             'regions': ['global'],
             'provider': 'gcp',
             'tags': a.get('tags', ()),
             'vars': _update(a.get('vars', {}), org_vars)}
        yield d
    for a in config.get("tenancies", ()):
        d = {"account_id": a["profile"],
             "name": a.get("name", a["profile"]),
             "regions": a.get("regions", ["global"]),
             "provider": "oci",
             "profile": a["profile"],
             "tags": a.get("tags", ()),
             "oci_compartments": a.get("vars", {}).get("oci_compartments"),
             "vars": _update(a.get("vars", {}), org_vars)}
        yield d


def _update(old, new):
    for k in new:
        old.setdefault(k, new[k])
    return old


def run_account(account, region, policies_config, output_path,
                cache_period, cache_path, metrics, dryrun, debug):
    """Execute a set of policies on an account.
    """
    logging.getLogger('custodian.output').setLevel(logging.ERROR + 1)
    CONN_CACHE.session = None
    CONN_CACHE.time = None
    load_available()

    output_path = join_output_path(output_path, account['name'], region)

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

    if account.get("oci_compartments"):
        env_vars.update({"OCI_COMPARTMENTS": account.get("oci_compartments")})

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


def initialize_provider_output(policies_config, output_dir, regions):
    """allow the provider an opportunity to initialize the output config.
    """
    # use just enough configuration to attempt to limit initialization
    # to the output dir. we pass in dummy values for several settings
    # that if missing would cause at least the aws or azure provider
    # to do additional dynamic lookups that aren't meaningful in the
    # context of c7n-org.
    policy_config = Config.empty(
        account_id='112233445566',
        output_dir=output_dir,
        region=regions and regions[0] or "us-east-1"
    )
    provider_name = get_policy_provider(policies_config['policies'][0])
    provider = cloud_providers[provider_name]()
    provider.initialize(policy_config)
    return policy_config.output_dir


@cli.command(name='run')
@click.option('-c', '--config', required=True, help="Accounts config file")
@click.option("-u", "--use", required=True)
@click.option('-s', '--output-dir', required=True, type=click.Path())
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('--not-accounts', multiple=True, default=None)
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
def run(config, use, output_dir, accounts, not_accounts, tags, region,
        policy, policy_tags, cache_period, cache_path, metrics,
        dryrun, debug, verbose, metrics_uri):
    """run a custodian policy across accounts"""
    accounts_config, custodian_config, executor = init(
        config, use, debug, verbose, accounts, tags, policy, policy_tags=policy_tags,
        not_accounts=not_accounts)
    if not (accounts_config["accounts"] and custodian_config["policies"]):
        log.info(
            "Targeting accounts: %d, policies: %d. Nothing to do." %
            (len(accounts_config["accounts"]), len(custodian_config["policies"]))
        )
        return

    policy_counts = Counter()
    success = True

    if metrics_uri:
        metrics = metrics_uri

    if not cache_path:
        cache_path = os.path.expanduser("~/.cache/c7n-org")
        if not os.path.exists(cache_path):
            os.makedirs(cache_path)

    output_dir = initialize_provider_output(custodian_config, output_dir, region)

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


if __name__ == "__main__":
    cli()
