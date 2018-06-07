import os
import re
from vcr_unittest import VCRTestCase

from c7n.schema import generate
from c7n.resources import load_resources
from c7n.testing import TestUtils

from c7n_azure.session import Session

load_resources()

C7N_SCHEMA = generate()
DEFAULT_SUBSCRIPTION_ID = 'ea42f556-5106-4743-99b0-c129bfa71a47'


class AzureVCRBaseTest(VCRTestCase):

    def _get_vcr_kwargs(self):
        return super(VCRTestCase, self)._get_vcr_kwargs(
            filter_headers=['Authorization',
                            'client-request-id',
                            'retry-after',
                            'x-ms-client-request-id',
                            'x-ms-correlation-request-id',
                            'x-ms-ratelimit-remaining-subscription-reads',
                            'x-ms-request-id',
                            'x-ms-routing-request-id',
                            'x-ms-gateway-service-instanceid',
                            'x-ms-ratelimit-remaining-tenant-reads',
                            'x-ms-served-by', ],
            before_record_request=self.request_callback
        )

    def _get_vcr(self, **kwargs):
        myvcr = super(VCRTestCase, self)._get_vcr(**kwargs)
        myvcr.register_matcher('azurematcher', self.azure_matcher)
        myvcr.match_on = ['azurematcher']
        return myvcr

    def azure_matcher(self, r1, r2):
        """Replace all subscription ID's and ignore api-version"""
        if [k for k in set(r1.query) if k[0] != 'api-version'] != [
                k for k in set(r2.query) if k[0] != 'api-version']:
            return False

        r1_path = re.sub(
            r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
            DEFAULT_SUBSCRIPTION_ID,
            r1.path)
        r2_path = re.sub(
            r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
            DEFAULT_SUBSCRIPTION_ID,
            r2.path)

        return r1_path == r2_path

    def request_callback(self, request):
        """Modify requests before saving"""
        if "/subscriptions/" in request.url:
            request.uri = re.sub(
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
                DEFAULT_SUBSCRIPTION_ID,
                request.url)
        if re.match('https://login.microsoftonline.com/([^/]+)/oauth2/token', request.uri):
            return None
        return request


class BaseTest(TestUtils, AzureVCRBaseTest):
    """ Azure base testing class.
    """

    @staticmethod
    def setup_account():
        # Find actual name of storage account provisioned in our test environment
        s = Session()
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        accounts = list(client.storage_accounts.list())
        matching_account = [a for a in accounts if a.name.startswith("cctstorage")]
        return matching_account[0]


def arm_template(template):
    def decorator(func):
        def wrapper(*args, **kwargs):
            template_file_path = os.path.dirname(__file__) + "/templates/" + template
            if not os.path.isfile(template_file_path):
                return args[0].fail("ARM template {} is not found".format(template_file_path))
            return func(*args, **kwargs)
        return wrapper
    return decorator
