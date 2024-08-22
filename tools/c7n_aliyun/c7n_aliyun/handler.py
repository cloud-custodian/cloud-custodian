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

# Load resource plugins
from c7n_aliyun.entry import initialize_aliyun

from c7n.config import Config
from c7n.loader import PolicyLoader

initialize_aliyun()

log = logging.getLogger('custodian.aliyun.functions')

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
    output_dir = '/tmp/' + str(uuid.uuid4())
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.warning("Unable to make output directory: {}".format(error))
    return output_dir
