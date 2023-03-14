# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import uuid

from c7n.config import Config
from c7n.loader import PolicyLoader
# Load resource plugins
from c7n_gcp.entry import initialize_gcp

initialize_gcp()

log = logging.getLogger('custodian.gcp.functions')

logging.getLogger().setLevel(logging.INFO)


def run(event, context=None):
    # policies file should always be valid in functions so do loading naively
    with open('config.json') as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        log.error('Invalid policy config')
        return False

    # setup execution options
    options = Config.empty(**policy_config.pop('execution-options', {}))
    options.update(
        policy_config['policies'][0].get('mode', {}).get('execution-options', {}))
    # if output_dir specified use that, otherwise make a temp directory
    if not options.output_dir:
        options['output_dir'] = get_tmp_output_dir()

    loader = PolicyLoader(options)
    policies = loader.load_data(policy_config, 'config.json', validate=False)
    if policies:
        for p in policies:
            log.info("running policy %s", p.name)
            p.validate()
            p.push(event, context)
    return True


def get_tmp_output_dir():
    output_dir = '/tmp/' + str(uuid.uuid4())  # nosec
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.warning("Unable to make output directory: {}".format(error))
    return output_dir
