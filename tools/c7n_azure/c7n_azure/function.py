import logging
import sys
from os.path import dirname, join

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(dirname(__file__)))

from c7n_azure import handler, entry
import azure.functions as func

def main(input):
    logging.info('Python HTTP trigger function processed a request.')

    logging.info("Running Azure Cloud Custodian Policy")

    context = {
        'config_file': join(dirname(__file__), 'config.json'),
        'auth_file': join(dirname(__file__), 'auth.json')
    }
    handler.run(None, context)

# Need to manually initialize c7n_azure
entry.initialize_azure()

# flake8: noqa