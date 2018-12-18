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
Lambda entry point
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n_azure.session import Session
from c7n_azure.constants import RESOURCE_STORAGE
from c7n_mailer.azure.azure_queue_processor import MailerAzureQueueProcessor


def start_c7n_mailer(logger, config, auth_file):
    try:
        logger.info('c7n_mailer starting...')
        session = Session(authorization_file=auth_file, resource=RESOURCE_STORAGE)
        mailer_azure_queue_processor = MailerAzureQueueProcessor(config, logger, session=session)
        mailer_azure_queue_processor.run()
    except Exception as e:
        logger.exception("Error starting mailer MailerAzureQueueProcessor(). \n Error: %s \n" % (e))
