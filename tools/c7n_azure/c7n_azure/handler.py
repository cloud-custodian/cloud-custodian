from c7n.policy import PolicyCollection
from c7n.resources import load_resources
from c7n.config import Config
import os
import uuid
import logging
import json

log = logging.getLogger('custodian.azure.functions')


def run(event, context):

    # policies file should always be valid in lambda so do loading naively
    with open(context['config_file']) as f:
        policy_config = json.load(f)

    if not policy_config or not policy_config.get('policies'):
        return False

        # Initialize output directory, we've seen occasional perm issues with
        # lambda on temp directory and changing unix execution users, so
        # use a per execution temp space.
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
