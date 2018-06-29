# Copyright 2018 Capital One Services, LLC
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

import json
import logging
import os
import uuid

from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.resources import load_resources

log = logging.getLogger('custodian.azure.functions')


def run(event, context):

    # policies file should always be valid in functions so do loading naively
    with open(context['config_file']) as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        return False

    # Initialize output directory
    output_dir = os.environ.get(
        'C7N_OUTPUT_DIR',
        '/tmp/' + str(uuid.uuid4()))
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.warning("Unable to make output directory: {}".format(error))

    options_overrides = \
        policy_config['policies'][0].get('mode', {}).get('execution-options', {})

    options_overrides['authorization_file'] = context['auth_file']

    if 'output_dir' not in options_overrides:
        options_overrides['output_dir'] = output_dir
    options = Config.empty(**options_overrides)

    load_resources()
    policies = PolicyCollection.from_data(policy_config, options)
    if policies:
        for p in policies:
            p.push(event, context)
    return True
