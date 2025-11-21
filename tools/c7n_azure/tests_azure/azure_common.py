# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
import email.utils as eut
import json
import logging
import os
import re
from c7n.vendored.distutils.util import strtobool
from functools import wraps
from time import sleep

import azure.core.polling
import msrest.polling
from c7n.config import Bag, Config
from c7n.policy import ExecutionContext
from c7n.schema import generate
from c7n.testing import TestUtils
from c7n.utils import local_session
# Ensure the azure provider is loaded.
from c7n_azure import provider  # noqa
from c7n_azure import constants, utils
from c7n_azure.session import Session
from c7n_azure.utils import ThreadHelper
from mock import patch
from msrest.pipeline import ClientRawResponse
from msrest.serialization import Model
from msrest.service_client import ServiceClient
from vcr_unittest import VCRTestCase

from .azure_serializer import AzureSerializer

BASE_FOLDER = os.path.dirname(__file__)
C7N_SCHEMA = generate()
DEFAULT_SUBSCRIPTION_ID = 'ea42f556-5106-4743-99b0-c129bfa71a47'
CUSTOM_SUBSCRIPTION_ID = '00000000-5106-4743-99b0-c129bfa71a47'
DEFAULT_USER_OBJECT_ID = '00000000-0000-0000-0000-000000000002'
DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000003'
DEFAULT_CLIENT_ID = '00000000-0000-0000-0000-000000000004'
DEFAULT_INSTRUMENTATION_KEY = '00000000-0000-0000-0000-000000000004'
DEFAULT_STORAGE_KEY = 'DEC0DEDITtVwMoyAuTz1LioKkC+gB/EpRlQKNIaszQEhVidjWyP1kLW1z+jo'\
                      '/MGFHKc+t+M20PxoraNCslng9w=='
DEFAULT_AZURE_CLOUD = 'AzureCloud'

GRAPH_RESPONSE = {
    "value": [
        {
            "NOTE": "THIS RESPONSE FAKED BY AZURE_COMMON.PY",
            "odata.type": "Microsoft.DirectoryServices.User",
            "objectType": "User",
            "objectId": DEFAULT_USER_OBJECT_ID,
            "displayName": "John Doe",
            "mail": "john@doe.com",
            "refreshTokensValidFromDateTime": "2018-08-22T20:37:43Z",
            "userPrincipalName": "john@doe.com"
        }
    ]
}

ACTIVITY_LOG_RESPONSE = {
    "value": [
        {
            "caller": "john@doe.com",
            "id": "/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourcegroups/"
                  "TEST_VM/providers/Microsoft.Compute/virtualMachines/cctestvm/events/"
                  "37bf930a-fbb8-4c8c-9cc7-057cc1805c04/ticks/636923208048336028",
            "operationName": {
                "value": "Microsoft.Compute/virtualMachines/write",
                "localizedValue": "Create or Update Virtual Machine"
            },
            "eventTimestamp": "2019-05-01T15:20:04.8336028Z"
        }
    ]
}

SERVICE_TAG_RESPONSE = {
    "values": [
        {
            "name": "ApiManagement",
            "id": "ApiManagement",
            "properties": {
                "addressPrefixes": [
                    "13.69.64.76/31",
                    "13.69.66.144/28",
                    "23.101.67.140/32",
                    "51.145.179.78/32",
                    "137.117.160.56/32"
                ]
            }
        },
        {
            "name": "ApiManagement.WestUS",
            "id": "ApiManagement.WestUS",
            "properties": {
                "addressPrefixes": [
                    "13.64.39.16/32",
                    "40.112.242.148/31",
                    "40.112.243.240/28"
                ]
            }
        }
    ]
}


logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logging.getLogger("urllib3").setLevel(logging.INFO)
logging.getLogger("vcr").setLevel(logging.WARNING)


class AzureVCRBaseTest(VCRTestCase):

    TEST_DATE = None
    cassette_name = None

    FILTERED_HEADERS = ['authorization',
                        'accept-encoding',
                        'client-request-id',
                        'retry-after',
                        'strict-transport-security',
                        'server',
                        'user-Agent',
                        'accept-language',
                        'connection',
                        'x-ms-client-request-id',
                        'x-ms-correlation-request-id',
                        'x-ms-keyvault-service-version',
                        'x-ms-keyvault-network-info',
                        'x-ms-keyvault-region',
                        'x-ms-ratelimit-remaining-subscription-reads',
                        'x-ms-request-id',
                        'x-ms-routing-request-id',
                        'x-ms-gateway-service-instanceid',
                        'x-ms-ratelimit-remaining-tenant-reads',
                        'x-ms-served-by',
                        'x-ms-cosmos-llsn',
                        'x-ms-last-state-change-utc',
                        'x-ms-xp-role',
                        'x-ms-gatewayversion',
                        'x-ms-global-committed-lsn',
                        'x-aspnet-version',
                        'x-content-type-options',
                        'x-powered-by',
                        'ocp-aad-diagnostics-server-name',
                        'ocp-aad-session-key',
                        'vary',
                        'pragma',
                        'transfer-encoding',
                        'expires',
                        'content-location']

    def __init__(self, *args, **kwargs):
        super(AzureVCRBaseTest, self).__init__(*args, **kwargs)
        self.vcr_enabled = not strtobool(os.environ.get('C7N_FUNCTIONAL', 'no'))

    def is_playback(self):
        # You can't do this in setup because it is actually required by the base class
        # setup (via our callbacks), but it is also not possible to do until the base class setup
        # has completed initializing the cassette instance.
        cassette_exists = not hasattr(self, 'cassette') or os.path.isfile(self.cassette._path)
        return self.vcr_enabled and cassette_exists

    def _get_cassette_name(self):
        test_method = getattr(self, self._testMethodName)
        name_override = getattr(test_method, 'cassette_name', None)
        method_name = name_override or self.cassette_name or self._testMethodName
        name = '{0}.{1}.yaml'.format(self.__class__.__name__,
                                     method_name)
        return os.path.join(BASE_FOLDER, 'cassettes', name)

    def _get_vcr_kwargs(self):
        return super(VCRTestCase, self)._get_vcr_kwargs(
            before_record_request=self._request_callback,
            before_record_response=self._response_callback,
            decode_compressed_response=True
        )

    def _get_vcr(self, **kwargs):
        myvcr = super(VCRTestCase, self)._get_vcr(**kwargs)
        myvcr.register_matcher('azure-matcher', self._azure_matcher)
        myvcr.match_on = ['azure-matcher', 'method']
        myvcr.register_serializer('azure-json', AzureSerializer())
        myvcr.serializer = 'azure-json'
        myvcr.path_transformer = AzureVCRBaseTest._json_extension

        # Block recording when using fake token (generally only used on build servers)
        if os.environ.get(constants.ENV_ACCESS_TOKEN) == "fake_token":
            myvcr.record_mode = 'none'

        return myvcr

    def _azure_matcher(self, r1, r2):
        """Replace all subscription ID's and ignore api-version"""
        if [(k[0].lower(), k[1].lower()) for k in set(r1.query) if k[0] != 'api-version'] != \
           [(k[0].lower(), k[1].lower()) for k in set(r2.query) if k[0] != 'api-version']:
            return False

        r1_path = AzureVCRBaseTest._replace_subscription_id(r1.path)
        r2_path = AzureVCRBaseTest._replace_subscription_id(r2.path)
        # Some APIs (e.g. lock) that receive scope seems to replace / with %2F
        r1_path = r1_path.replace('%2F', '/').lower()
        r2_path = r2_path.replace('%2F', '/').lower()

        r1_path = r1_path.replace('//', '/').lower()
        r2_path = r2_path.replace('//', '/').lower()
        return r1_path == r2_path

    def _request_callback(self, request):
        """Modify requests before saving"""
        request.uri = AzureVCRBaseTest._replace_subscription_id(request.uri)
        request.uri = AzureVCRBaseTest._replace_tenant_id(request.uri)

        if request.body:
            request.body = b'mock_body'

        # Request headers serve no purpose as only URI is read during a playback.
        request.headers = None

        if re.match('https://login.microsoftonline.com/([^/]+)', request.uri):
            return None

        return request

    def _response_callback(self, response):
        if self.is_playback():
            if 'data' in response['body']:
                body = json.dumps(response['body']['data'])
                response['body']['string'] = body.encode('utf-8')
                response['headers']['content-length'] = [str(len(body))]

            return response

        response['headers'] = {k.lower(): v for (k, v) in
                               response['headers'].items()
                               if k.lower() not in self.FILTERED_HEADERS}

        content_type = response['headers'].get('content-type', (None,))[0]
        if not content_type or 'application/json' not in content_type:
            return response

        body = response['body'].pop('string').decode('utf-8')

        # Clean up subscription IDs and storage keys
        body = AzureVCRBaseTest._replace_tenant_id(body)
        body = AzureVCRBaseTest._replace_subscription_id(body)
        body = AzureVCRBaseTest._replace_storage_keys(body)
        body = AzureVCRBaseTest._replace_instrumentation_key(body)

        try:
            response['body']['data'] = json.loads(body)
        except json.decoder.JSONDecodeError:
            self.fail("AzureVCRBaseTest could not parse JSON response body "
                      "while attempting to record cassette. Body:\n%s" % body)

        # Replace some API responses entirely
        response = AzureVCRBaseTest._response_substitutions(response)

        return response

    @staticmethod
    def _response_substitutions(response):
        data = response['body']['data']

        if isinstance(data, dict):
            # Replace service tag responses
            if data.get('type', '') == 'Microsoft.Network/serviceTags':
                response['body']['data'] = SERVICE_TAG_RESPONSE
                return response

            # Replace AD graph responses
            odata_metadata = data.get('odata.metadata')
            if odata_metadata and "directoryObjects" in odata_metadata:
                response['body']['data'] = GRAPH_RESPONSE
                return response

            # Replace Activity Log API responses
            value_array = data.get('value', [])
            if value_array and \
                    isinstance(value_array[0], dict) and \
                    value_array[0].get('eventTimestamp'):
                response['body']['data'] = ACTIVITY_LOG_RESPONSE
                return response

            if 'authorizations' in data:
                response['body']['data']['authorizations'] = []

            # Real resource type responses are critical to catching
            # API version failures, but we can get rid of extra fields
            # and save a lot of space
            if 'resourceTypes' in data:
                response['body']['data']['resourceTypes'] = \
                    [{
                        'resourceType': r['resourceType'],
                        'apiVersions': [next(iter(r['apiVersions']))]
                    } for r in data['resourceTypes']]

        return response

    @staticmethod
    def _replace_subscription_id(s):
        prefixes = ['(/|%2F)?subscriptions(/|%2F)',
                    '"subscription":\\s*"']
        regex = r"(?P<prefix>(%s))" \
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}" \
                % '|'.join(['(%s)' % p for p in prefixes])

        match = re.search(regex, s)

        if match is not None:
            sub_id = match.group(0)
            s = s.replace(sub_id[-36:], DEFAULT_SUBSCRIPTION_ID)
            s = s.replace(sub_id[-12:], DEFAULT_SUBSCRIPTION_ID[-12:])
        else:
            # For function apps
            func_regex = r"^https\:\/\/[\w-]+([a-f0-9]{12})\.(blob\.core|scm\.azurewebsites)"
            func_match = re.search(func_regex, s)
            if func_match is not None:
                sub_fragment = func_match.group(1)
                s = s.replace(sub_fragment, DEFAULT_SUBSCRIPTION_ID[-12:])

        return s

    @staticmethod
    def _replace_tenant_id(s):
        prefixes = ['(/|%2F)graph.windows.net(/|%2F)',
                    '"(t|T)enantId":\\s*"']
        regex = r"(?P<prefix>(%s))" \
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}" \
                % '|'.join(['(%s)' % p for p in prefixes])

        return re.sub(regex, r"\g<prefix>" + DEFAULT_TENANT_ID, s)

    @staticmethod
    def _replace_storage_keys(s):
        # All usages of storage keys have the word "key" somewhere
        if "key" in s.lower():
            return re.sub(
                r"(?P<prefix>=|\"|:)(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==)",
                r"\g<prefix>" + DEFAULT_STORAGE_KEY, s)
        return s

    @staticmethod
    def _replace_instrumentation_key(s):
        prefixes = ['"InstrumentationKey":\\s*"']

        regex = r"(?P<prefix>(%s))" \
                r"[\da-zA-Z]{8}-([\da-zA-Z]{4}-){3}[\da-zA-Z]{12}" \
                % '|'.join(['(%s)' % p for p in prefixes])

        return re.sub(regex, r"\g<prefix>" + DEFAULT_INSTRUMENTATION_KEY, s)

    @staticmethod
    def _json_extension(path):
        # A simple transformer keeps the native
        # cassette naming logic in place
        return path[:-4] + "json"


class BaseTest(TestUtils, AzureVCRBaseTest):

    test_context = ExecutionContext(
        Session,
        Bag(name="xyz", provider_name='azure'),
        Config.empty()
    )

    """ Azure base testing class.
    """
    def __init__(self, *args, **kwargs):
        super(BaseTest, self).__init__(*args, **kwargs)
        self._requires_polling = False

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(BaseTest, cls).setUpClass(*args, **kwargs)

    @classmethod
    def tearDownClass(cls, *args, **kwargs):
        super(BaseTest, cls).tearDownClass(*args, **kwargs)

    def setUp(self):
        super(BaseTest, self).setUp()
        ThreadHelper.disable_multi_threading = True

        # We always patch the date for recordings so URLs that involve dates match up
        if self.vcr_enabled:
            self._utc_patch = patch.object(utils, 'utcnow', self._get_test_date)
            self._utc_patch.start()
            self.addCleanup(self._utc_patch.stop)

            self._now_patch = patch.object(utils, 'now', self._get_test_date)
            self._now_patch.start()
            self.addCleanup(self._now_patch.stop)

        if self.is_playback():
            if self._requires_polling:
                # If using polling we need to monkey patch the timeout during playback
                # or we'll have long sleeps introduced into our test runs
                Session._old_client = Session.client
                Session.client = BaseTest.session_client_wrapper
                self.addCleanup(BaseTest.session_client_cleanup)
            else:
                # Patch Poller with constructor that always disables polling
                # This breaks blocking on long running operations (resource creation).
                self._lro_patch = patch.object(azure.core.polling.LROPoller,
                                               '__init__',
                                               BaseTest.lro_init)
                self._lro_patch.start()
                self.addCleanup(self._lro_patch.stop)

                # We still have a few legacy clients, so keep this code.
                self._lro_patch_legacy = patch.object(msrest.polling.LROPoller,
                                                      '__init__',
                                                      BaseTest.lro_init_legacy)
                self._lro_patch_legacy.start()
                self.addCleanup(self._lro_patch_legacy.stop)

            if constants.ENV_ACCESS_TOKEN in os.environ:
                self._tenant_patch = patch('c7n_azure.session.Session.get_tenant_id',
                                           return_value=DEFAULT_TENANT_ID)
                self._tenant_patch.start()
                self.addCleanup(self._tenant_patch.stop)

            self._subscription_patch = patch('c7n_azure.session.Session.get_subscription_id',
                                             return_value=DEFAULT_SUBSCRIPTION_ID)
            self._subscription_patch.start()
            self.addCleanup(self._subscription_patch.stop)

        self.session = local_session(Session)

    def _get_test_date(self, tz=None):
        header_date = self.cassette.responses[0]['headers'].get('date') \
            if self.cassette.responses else None

        if header_date:
            test_date = datetime.datetime(*eut.parsedate(header_date[0])[:6])
        else:
            return datetime.datetime.now(tz=tz)
        return test_date.replace(hour=23, minute=59, second=59, microsecond=0)

    def sleep_in_live_mode(self, interval=60):
        if not self.is_playback():
            sleep(interval)

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
    def lro_init(self, client, initial_response, deserialization_callback, polling_method):
        self._client = client
        self._response = initial_response.response if \
            isinstance(initial_response, ClientRawResponse) else \
            initial_response
        self._callbacks = []  # type List[Callable]
        self._polling_method = azure.core.polling.NoPolling()

        if isinstance(deserialization_callback, type) and \
                issubclass(deserialization_callback, Model):
            deserialization_callback = deserialization_callback.deserialize

        # Might raise a AzureError
        self._polling_method.initialize(self._client, self._response, deserialization_callback)

        self._thread = None
        self._done = None
        self._exception = None

    @staticmethod
    def lro_init_legacy(self, client, initial_response, deserialization_callback, polling_method):
        self._client = client if isinstance(client, ServiceClient) else client._client
        self._response = initial_response.response if \
            isinstance(initial_response, ClientRawResponse) else \
            initial_response
        self._callbacks = []  # type List[Callable]
        self._polling_method = msrest.polling.NoPolling()

        if isinstance(deserialization_callback, type) and \
                issubclass(deserialization_callback, Model):
            deserialization_callback = deserialization_callback.deserialize

        # Might raise a CloudError
        self._polling_method.initialize(self._client, self._response, deserialization_callback)

        self._thread = None
        self._done = None
        self._exception = None

    @staticmethod
    def session_client_cleanup():
        Session.client = Session._old_client

    @staticmethod
    def session_client_wrapper(self, client, vault_url=None):
        client = Session._old_client(self, client)
        # TODO: Is there a way to override it properly instead of hijacking?
        if hasattr(client, '_config'):
            client._config.polling_interval = 0
        # TODO: Legacy clients.. Just in case
        if hasattr(client, 'config'):
            client.config.long_running_operation_timeout = 0
        return client


def arm_template(template):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            template_file_path = os.path.join(BASE_FOLDER, "templates", template)
            if not os.path.isfile(template_file_path):
                return args[0].fail("ARM template {} is not found".format(template_file_path))
            return func(*args, **kwargs)
        return wrapper
    return decorator


def cassette_name(name):
    def decorator(func):
        func.cassette_name = name
        return func
    return decorator


def requires_arm_polling(cls):
    orig_init = cls.__init__
    # Make copy of original __init__, so we can call it without recursion

    def __init__(self, *args, **kws):
        orig_init(self, *args, **kws)  # Call the original __init__
        self._requires_polling = True

    cls.__init__ = __init__  # Set the class' __init__ to the new one
    return cls
