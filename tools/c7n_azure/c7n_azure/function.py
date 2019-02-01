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

import logging
import sys

from os.path import dirname, join

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(dirname(__file__)))

from c7n_azure import handler, entry

try:
    import azure.functions as func
    from azure.functions_worker.bindings.queue import QueueMessage
except ImportError:
    pass

max_dequeue_count = 3

def main(input):
    logging.info("Running Azure Cloud Custodian Policy")

    context = {
        'config_file': join(dirname(__file__), 'config.json'),
        'auth_file': join(dirname(__file__), 'auth.json')
    }

    event = None

    if type(input) is QueueMessage:
        if input.dequeue_count > max_dequeue_count:
            return
        event = input.get_json()

    handler.run(event, context)


# Need to manually initialize c7n_azure
entry.initialize_azure()

# flake8: noqa