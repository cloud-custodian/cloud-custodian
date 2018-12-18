# Copyright 2015-2018 Capital One Services, LLC
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
import datetime
import os
import re

from c7n_azure import constants
from c7n_azure.session import Session
from c7n_azure.utils import ThreadHelper
from mock import patch
from vcr_unittest import VCRTestCase

from c7n.resources import load_resources
from c7n.schema import generate
from c7n.testing import TestUtils

import msrest.polling
from msrest.serialization import Model
from msrest.service_client import ServiceClient
from msrest.pipeline import ClientRawResponse

load_resources()

C7N_SCHEMA = generate()
DEFAULT_SUBSCRIPTION_ID = 'ea42f556-5106-4743-99b0-c129bfa71a47'
# latest VCR recording date that tag tests
# If tests need to be re-recorded, update to current date
TEST_DATE = datetime.datetime(2018, 9, 10, 23, 59, 59)


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

        # Block recording when using fake token (tox runs)
        if os.environ.get(constants.ENV_ACCESS_TOKEN) == "fake_token":
            myvcr.record_mode = 'none'

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

        r1_path = r1_path.replace('//', '/')
        r2_path = r2_path.replace('//', '/')

        return r1_path == r2_path

    def request_callback(self, request):
        """Modify requests before saving"""
        if "/subscriptions/" in request.url:
            request.uri = re.sub(
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}",
                DEFAULT_SUBSCRIPTION_ID,
                request.url)
        if request.body:
            request.body = b'mock_body'
        if re.match('https://login.microsoftonline.com/([^/]+)/oauth2/token', request.uri):
            return None
        if re.match('https://login.microsoftonline.com/([^/]+)/oauth2/token', request.uri):
            return None
        return request


class BaseTest(TestUtils, AzureVCRBaseTest):
    """ Azure base testing class.
    """

    def setUp(self):
        super(BaseTest, self).setUp()
        ThreadHelper.disable_multi_threading = True

        # Patch Poller with constructor that always disables polling
        self.lro_patch = patch.object(msrest.polling.LROPoller, '__init__', BaseTest.lro_test_init)
        self.lro_patch.start()

    def tearDown(self):
        super(BaseTest, self).tearDown()
        self.lro_patch.stop()

    @staticmethod
    def setup_account():
        # Find actual name of storage account provisioned in our test environment
        s = Session()
        client = s.client('azure.mgmt.storage.StorageManagementClient')
        accounts = list(client.storage_accounts.list())
        matching_account = [a for a in accounts if a.name.startswith("cctstorage")]
        return matching_account[0]

    @staticmethod
    def sign_out_patch():
        return patch.dict(os.environ,
                          {
                              constants.ENV_TENANT_ID: '',
                              constants.ENV_SUB_ID: '',
                              constants.ENV_CLIENT_ID: '',
                              constants.ENV_CLIENT_SECRET: ''
                          }, clear=True)

    @staticmethod
    def lro_test_init(self, client, initial_response, deserialization_callback, polling_method):
        self._client = client if isinstance(client, ServiceClient) else client._client
        self._response = initial_response.response if \
            isinstance(initial_response, ClientRawResponse) else \
            initial_response
        self._callbacks = []  # type: List[Callable]
        self._polling_method = msrest.polling.NoPolling()

        if isinstance(deserialization_callback, type) and \
                issubclass(deserialization_callback, Model):
            deserialization_callback = deserialization_callback.deserialize

        # Might raise a CloudError
        self._polling_method.initialize(self._client, self._response, deserialization_callback)

        self._thread = None
        self._done = None
        self._exception = None


def arm_template(template):
    def decorator(func):
        def wrapper(*args, **kwargs):
            template_file_path = os.path.dirname(__file__) + "/templates/" + template
            if not os.path.isfile(template_file_path):
                return args[0].fail("ARM template {} is not found".format(template_file_path))
            return func(*args, **kwargs)
        return wrapper
    return decorator
