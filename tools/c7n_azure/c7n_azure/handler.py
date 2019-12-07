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

from c7n.utils import reset_session_cache
from c7n.config import Config
from c7n.policy import PolicyCollection
from c7n.resources import load_resources

from c7n_azure.provider import Azure

log = logging.getLogger('custodian.azure.functions')


def run(event, context, subscription_id=None):
    # Always reset session cache before the run.. If there is any issue with configuration,
    # if next run happens in the same process, it might have different target subscription id.
    reset_session_cache()

    # policies file should always be valid in functions so do loading naively
    with open(context['config_file']) as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        log.error('Invalid policy config')
        return False

    options_overrides = \
        policy_config['policies'][0].get('mode', {}).get('execution-options', {})

    # setup our auth file location on disk
    options_overrides['authorization_file'] = context['auth_file']

    # if output_dir specified use that, otherwise make a temp directory
    if 'output_dir' not in options_overrides:
        options_overrides['output_dir'] = get_tmp_output_dir()

    # merge all our options in
    options = Config.empty(**options_overrides)

    if subscription_id is not None:
        options['account_id'] = subscription_id

    load_resources()

    options = Azure().initialize(options)

    policies = PolicyCollection.from_data(policy_config, options)
    if policies:
        for p in policies:
            try:
                p.push(event, context)
            except Exception as error:
                log.error("Unable to process policy: %s :: %s" % (p.name, error))

    return True


def get_tmp_output_dir():
    output_dir = '/tmp/' + str(uuid.uuid4())
    if not os.path.exists(output_dir):
        try:
            os.mkdir(output_dir)
        except OSError as error:
            log.error("Unable to make output directory: {}".format(error))
    return output_dir
