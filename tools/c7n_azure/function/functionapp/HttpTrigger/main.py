import logging
import sys
from os.path import dirname

# The working path for the Azure Function doesn't include this file's folder
sys.path.append(dirname(dirname(__file__)))

from c7n_azure import handler, entry
import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    logging.info("Running Azure Cloud Custodian Policy")
    handler.run(None, None)

    return func.HttpResponse("Running Azure Cloud Custodian Policy")

# Need to manually initalize the c7n_azure
entry.initialize_azure()
