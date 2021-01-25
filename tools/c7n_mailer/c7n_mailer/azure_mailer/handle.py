# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Lambda entry point
"""
from c7n_azure.session import Session
from c7n_azure.constants import RESOURCE_STORAGE
from c7n_mailer.azure_mailer.azure_queue_processor import MailerAzureQueueProcessor


def start_c7n_mailer(logger, config, auth_file):
    try:
        logger.info('c7n_mailer starting...')
        session = Session(authorization_file=auth_file, resource=RESOURCE_STORAGE)
        mailer_azure_queue_processor = MailerAzureQueueProcessor(config, logger, session=session)
        mailer_azure_queue_processor.run()
    except Exception as e:
        logger.exception("Error starting mailer MailerAzureQueueProcessor(). \n Error: %s \n" % (e))
