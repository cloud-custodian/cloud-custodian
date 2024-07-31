# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Cloud-Custodian AWS Lambda Entry Point
"""
import os
import logging
import json

from c7n.config import Config
from c7n.structure import StructureParser
from c7n.resources import load_resources
from c7n.resources.aws import AWS
from c7n.policy import PolicyCollection
from c7n.utils import format_event, get_account_id_from_sts, local_session

import boto3

logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
log = logging.getLogger('custodian.lambda')

##########################################
#
# Env var AWS Lambda specific configuration options, these are part of
# our "public" interface and hence are subject to compatiblity constraints.
#
# Control whether custodian lambda policy skips events that represent errors.
# We default to skipping events which denote they have errors.
# Set with `export C7N_SKIP_EVTERR=no` to process error events
C7N_SKIP_EVTERR = True

# Control whether the triggering event is logged.
# Set with `export C7N_DEBUG_EVENT=no` to disable event logging.
C7N_DEBUG_EVENT = True

# Control whether a policy failure will result in a lambda execution failure.
# Lambda on error will report error metrics and depending on event source
# automatically retry.
# Set with `export C7N_CATCH_ERR=yes`
C7N_CATCH_ERR = False


##########################################
#
# Internal global variables
#

# config.json policy data dict
policy_data = None

# execution options for the policy
policy_config = None


def init_env_globals():
    """Set module level values from environment variables.

    Encapsulated here to enable better testing.
    """
    global C7N_SKIP_EVTERR, C7N_DEBUG_EVENT, C7N_CATCH_ERR

    C7N_SKIP_EVTERR = os.environ.get(
        'C7N_SKIP_ERR_EVENT', 'yes') == 'yes' and True or False

    C7N_DEBUG_EVENT = os.environ.get(
        'C7N_DEBUG_EVENT', 'yes') == 'yes' and True or False

    C7N_CATCH_ERR = os.environ.get(
        'C7N_CATCH_ERR', 'no').strip().lower() == 'yes' and True or False


def init_config(policy_config):
    """Get policy lambda execution configuration.

    cli parameters are serialized into the policy lambda config,
    we merge those with any policy specific execution options.

    --assume role and -s output directory get special handling, as
    to disambiguate any cli context.

    account id is sourced from the config options or from api call
    and cached as a global.

    Todo: this should get refactored out to mu.py as part of the
    write out of configuration, instead of runtime processed.
    """
    exec_options = policy_config.get('execution-options', {})

    # Remove some configuration options that don't make sense to translate from
    # cli to lambda automatically.
    #  - assume role on cli doesn't translate, it is the default lambda role and
    #    used to provision the lambda.
    #  - profile doesnt translate to lambda its `home` dir setup dependent
    #  - dryrun doesn't translate (and shouldn't be present)
    #  - region doesn't translate from cli (the lambda is bound to a region), and
    #    on the cli represents the region the lambda is provisioned in.
    for k in ('assume_role', 'profile', 'region', 'dryrun', 'cache'):
        exec_options.pop(k, None)

    # a cli local directory doesn't translate to lambda
    if not exec_options.get('output_dir', '').startswith('s3'):
        exec_options['output_dir'] = '/tmp'  # nosec

    account_id = None
    # we can source account id from the cli parameters to avoid the sts call
    if exec_options.get('account_id'):
        account_id = exec_options['account_id']

    # merge with policy specific configuration
    exec_options.update(
        policy_config['policies'][0].get('mode', {}).get('execution-options', {}))

    # if using assume role in lambda ensure that the correct
    # execution account is captured in options.
    if 'assume_role' in exec_options:
        account_id = exec_options['assume_role'].split(':')[4]
    elif account_id is None:
        session = local_session(boto3.Session)
        account_id = get_account_id_from_sts(session)
    exec_options['account_id'] = account_id

    # Historical compatibility with manually set execution options
    # previously this was a boolean, its now a string value with the
    # boolean flag triggering a string value of 'aws'
    if 'metrics_enabled' in exec_options \
       and isinstance(exec_options['metrics_enabled'], bool) \
       and exec_options['metrics_enabled']:
        exec_options['metrics_enabled'] = 'aws'

    config = Config.empty(**exec_options)
    return AWS().initialize(config)


# One time initilization of global environment settings
init_env_globals()


def dispatch_event(event, context):
    # default event.detail for EB Scheduler is '{}', not {}
    if event.get('detail') == '{}':
        event['detail'] = {}
    error = event.get('detail', {}).get('errorCode')
    if error and C7N_SKIP_EVTERR:
        log.debug("Skipping failed operation: %s" % error)
        return

    # one time initialization for cold starts.
    global policy_config, policy_data
    if policy_config is None:
        with open('config.json') as f:
            policy_data = json.load(f)
        policy_config = init_config(policy_data)
        load_resources(StructureParser().get_resource_types(policy_data))

    if C7N_DEBUG_EVENT:
        event['debug'] = True
        log.info("Processing event\n %s", format_event(event))

    if not policy_data or not policy_data.get('policies'):
        return False

    policies = PolicyCollection.from_data(policy_data, policy_config)
    for p in policies:
        try:
            # validation provides for an initialization point for
            # some filters/actions.
            p.validate()
            p.push(event, context)
        except Exception:
            log.exception("error during policy execution")
            if C7N_CATCH_ERR:
                continue
            raise
    return True
