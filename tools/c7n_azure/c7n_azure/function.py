# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import sys

from os.path import dirname, join

function_directory = dirname(__file__)

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(function_directory))

from c7n_azure import handler, entry
from c7n_azure.utils import ResourceIdParser
from azure.functions import QueueMessage

max_dequeue_count = 3

def main(input):
    logging.info("Running Azure Cloud Custodian Policy %s", input)

    context = {
        'config_file': join(function_directory, 'config.json'),
        'auth_file': join(function_directory, 'auth.json')
    }

    event = None
    subscription_id = None

    if isinstance(input, QueueMessage):
        if input.dequeue_count > max_dequeue_count:
            return
        event = input.get_json()
        subscription_id = ResourceIdParser.get_subscription_id(event['subject'])

    handler.run(event, context, subscription_id)


# Need to manually initialize c7n_azure
entry.initialize_azure()

# flake8: noqa
