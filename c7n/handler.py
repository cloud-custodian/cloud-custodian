# Copyright 2016-2017 Capital One Services, LLC
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
"""
Cloud-Custodian Lambda Entry Point

Mostly this serves to load up the policy and dispatch
an event.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import uuid
import logging
import json

from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.utils import format_event, get_account_id_from_sts
from c7n.config import Config

import boto3

logging.root.setLevel(logging.DEBUG)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
log = logging.getLogger('custodian.lambda')

#
# Env serverless specific configuration options, these are part of "public" interface
#
# We default to skipping events which denote they have errors
C7N_SKIP_EVTERR = os.environ.get('C7N_SKIP_ERR_EVENT', 'yes') == 'yes' and True or False

# We default to logging the full event that triggered lambda execution
C7N_DEBUG_EVENT = os.environ.get('C7N_DEBUG_EVENT', 'yes') == 'yes' and True or False

# We default to not catching policy errors in lambda, which will lead to retry behavior
C7N_CATCH_ERR = os.environ.get('C7N_CATCH_ERR', 'no').strip().lower() == 'yes' and True or False

#
# Internal global variables
#
# Default global cache of execution account id for initial configuration setup.
account_id = None

# config.json policy data dict
policy_config = None

# On cold start load all resources, requires a pythonpath directory scan
if 'AWS_EXECUTION_ENV' in os.environ:
    load_resources()


def get_local_output_dir():
    """Create a local output directory per execution.

    We've seen occassional (1/100000) perm issues with lambda on temp
    directory and changing unix execution users (2015-2018), so use a
    per execution temp space. With firecracker lambdas this may be outdated.
    """
    output_dir = os.environ.get('C7N_OUTPUT_DIR', '/tmp/' + str(uuid.uuid4()))
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.warning("Unable to make output directory: {}".format(error))
    return output_dir


def init_config(policy_config):
    """Get policy lambda execution configuration.

    cli parameters are serialized into the policy lambda config,
    we merge those with any policy specific execution options.

    --assume role and -s output directory get special handling, as
    to disambiguate any cli context.

    account id is sourced from the config options or from api call
    and cached as a global
    """
    global account_id

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
        exec_options['output_dir'] = get_local_output_dir()

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
        session = boto3.Session()
        account_id = get_account_id_from_sts(session)
    exec_options['account_id'] = account_id

    # Historical compatibility with manually set execution options
    # previously this was a boolean, its now a string value with the
    # boolean flag triggering a string value of 'aws'
    if 'metrics_enabled' in exec_options \
       and isinstance(exec_options['metrics_enabled'], bool) \
       and exec_options['metrics_enabled']:
        exec_options['metrics_enabled'] = 'aws'

    return Config.empty(**exec_options)


def dispatch_event(event, context):
    error = event.get('detail', {}).get('errorCode')
    if error and C7N_SKIP_EVTERR:
        log.debug("Skipping failed operation: %s" % error)
        return

    if C7N_DEBUG_EVENT:
        event['debug'] = True
        log.info("Processing event\n %s", format_event(event))

    # Policies file should always be valid in lambda so do loading naively
    global policy_config
    if policy_config is None:
        with open('config.json') as f:
            policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        return False

    options = init_config(policy_config)

    policies = PolicyCollection.from_data(policy_config, options)
    if policies:
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
