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
import json
from os.path import dirname, join

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(dirname(__file__)))

from c7n_mailer.azure_mailer import handle

def main(input):
    logger = logging.getLogger('custodian.mailer')
    config_file = join(dirname(__file__), 'config.json')
    with open(config_file) as fh:
        config = json.load(fh)
    return handle.start_c7n_mailer(logger, config, join(dirname(__file__), 'auth.json'))

# flake8: noqa
