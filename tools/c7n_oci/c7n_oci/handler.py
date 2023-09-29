# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import io
import json
import logging
import os
import uuid

import yaml
from c7n_oci.provider import OCI

from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.structure import StructureParser
from c7n.utils import reset_session_cache

log = logging.getLogger("custodian.oci.functions")
logging.getLogger().setLevel(logging.INFO)


def handler(ctx, data: io.BytesIO = None):
    log.info("Starting Function execution")
    try:
        body = json.loads(data.getvalue())
        log.debug(f"Recieved Body {str(body)}")
    except (Exception, ValueError) as ex:
        log.error("Error parsing json payload: ")
        log.exception(ex)
        raise ex

    run(body, ctx)
    log.info("Function execution is completed")


def run(event, ctx):
    function_config = ctx.Config()
    policy_string = function_config.get("policy")
    policy = {}

    if policy_string:
        policy = yaml.safe_load(policy_string)
    else:
        log.error("No policy found in function configuration")
        return False

    if not policy.get("policies"):
        log.error("Invalid policy config")
        return False

    options = function_config.get('execution-options', {})
    if options:
        options = json.loads(options)

    if not options.get('output_dir'):
        options['output_dir'] = get_tmp_output_dir()

    options.update(policy['policies'][0].get('mode', {}).get('execution-options', {}))
    options = Config.empty(**options)

    load_resources(StructureParser().get_resource_types(policy))
    options = OCI().initialize(options)
    policies = PolicyCollection.from_data(policy, options)

    if policies:
        for p in policies:
            log.info("Running policy %s", p.name)
            p.validate()
            p.push(event)

    reset_session_cache()
    return True


def get_tmp_output_dir():
    output_dir = "/tmp/" + str(uuid.uuid4())  # nosec
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.error("Unable to make output directory: {}".format(error))
            raise error
    return output_dir
