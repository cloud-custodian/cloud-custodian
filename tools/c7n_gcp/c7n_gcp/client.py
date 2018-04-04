# Copyright 2017 The Forseti Security Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Base GCP client which uses the discovery API."""
import logging
import threading
from googleapiclient import discovery
import httplib2
from oauth2client import client
import os
from ratelimiter import RateLimiter
from retrying import retry
import socket
import ssl

from six.moves import http_client
from six.moves.urllib.error import URLError

CLOUD_SCOPES = frozenset(['https://www.googleapis.com/auth/cloud-platform'])

# Per request max wait timeout.
HTTP_REQUEST_TIMEOUT = 30.0

# Per thread storage.
LOCAL_THREAD = threading.local()

log = logging.getLogger('c7n_gcp.client')

# Default value num_retries within HttpRequest execute method
NUM_HTTP_RETRIES = 5

RETRYABLE_EXCEPTIONS = (
    http_client.ResponseNotReady,
    http_client.IncompleteRead,
    httplib2.ServerNotFoundError,
    socket.error,
    ssl.SSLError,
    URLError,  # include "no network connection"
)


class PaginationNotSupported(Exception):
    """Pagination not supported on this api."""


def is_retryable_exception(e):
    """Whether exception should be retried.

    Args:
        e (Exception): Exception object.

    Returns:
        bool: True for exceptions to retry. False otherwise.
    """
    return isinstance(e, RETRYABLE_EXCEPTIONS)


@retry(retry_on_exception=is_retryable_exception,
       wait_exponential_multiplier=1000,
       wait_exponential_max=10000,
       stop_max_attempt_number=5)
def _create_service_api(credentials, service_name, version, developer_key=None,
                        cache_discovery=False):
    """Builds and returns a cloud API service object.

    Args:
        credentials (OAuth2Credentials): Credentials that will be used to
            authenticate the API calls.
        service_name (str): The name of the API.
        version (str): The version of the API to use.
        developer_key (str): The api key to use to determine the project
            associated with the API call, most API services do not require
            this to be set.
        cache_discovery (bool): Whether or not to cache the discovery doc.

    Returns:
        object: A Resource object with methods for interacting with the service.
    """
    # The default logging of the discovery obj is very noisy in recent versions.
    # Lower the default logging level of just this module to WARNING unless
    # debug is enabled.
    if log.getEffectiveLevel() > logging.DEBUG:
        logging.getLogger(discovery.__name__).setLevel(logging.WARNING)

    discovery_kwargs = {
        'serviceName': service_name,
        'version': version,
        'developerKey': developer_key,
        'cache_discovery': cache_discovery,
        'credentials': credentials}
    return discovery.build(**discovery_kwargs)


def _set_ua_and_scopes(credentials, sw_name, sw_version):
    """Set custom Forseti user agent and add cloud scopes on credential object.

    Args:
        credentials (client.OAuth2Credentials): The credentials object used to
            authenticate all http requests.

    Returns:
        client.OAuth2Credentials: The credentials object with the user agent
            attribute set or updated.
    """
    if isinstance(credentials, client.OAuth2Credentials):
        credentials.user_agent = (
            'Python-httplib2/{} (gzip), {}/{}'.format(
                httplib2.__version__,
                sw_name,
                sw_version))
        if (isinstance(credentials, client.GoogleCredentials) and
                credentials.create_scoped_required()):
            credentials = credentials.create_scoped(list(CLOUD_SCOPES))
    return credentials


class Session(object):
    """Base class for API repository for a specified Cloud API."""

    def __init__(self,
                 credentials=None,
                 quota_max_calls=None,
                 quota_period=None,
                 use_rate_limiter=False,
                 **kwargs):
        """Constructor.

        Args:
            api_name (str): The API name to wrap. More details here:
                  https://developers.google.com/api-client-library/python/apis/
            versions (list): A list of version strings to initialize.
            credentials (object): GoogleCredentials.
            quota_max_calls (int): Allowed requests per <quota_period> for the
                API.
            quota_period (float): The time period to track requests over.
            use_rate_limiter (bool): Set to false to disable the use of a rate
                limiter for this service.
            **kwargs (dict): Additional args such as version.
        """
        self._use_cached_http = False
        if not credentials:
            # Only share the http object when using the default credentials.
            self._use_cached_http = True
            credentials = client.GoogleCredentials.get_application_default()
        self._credentials = _set_ua_and_scopes(credentials, 'custodian-gcp', '0.1')
        if use_rate_limiter:
            self._rate_limiter = RateLimiter(max_calls=quota_max_calls,
                                             period=quota_period)
        else:
            self._rate_limiter = None

    def __repr__(self):
        """The object representation.

        Returns:
            str: The object representation.
        """
        return '<GCPSession: name=%s, versions=%s>' % (
            self.name, self.versions)

    def client(self, service_name, version, component, **kw):
        """Safely initialize a repository class to a property.

        Args:
            repository_class (class): The class to initialize.
            version (str): The gcp service version for the repository.

        Returns:
            object: An instance of repository_class.
        """

        service = _create_service_api(
            self._credentials,
            service_name,
            version,
            kw.get('developer_key'),
            kw.get('cache_discovery', False))

        return ServiceClient(
            gcp_service=service,
            component=component,
            credentials=self._credentials,
            rate_limiter=self._rate_limiter,
            use_cached_http=self._use_cached_http)


# pylint: disable=too-many-instance-attributes, too-many-arguments
class ServiceClient(object):
    """Base class for GCP APIs."""

    def __init__(self, gcp_service, credentials, component=None,
                 num_retries=NUM_HTTP_RETRIES, key_field='project',
                 entity_field=None, list_key_field=None, get_key_field=None,
                 max_results_field='maxResults', search_query_field='query',
                 rate_limiter=None, use_cached_http=True):
        """Constructor.

        Args:
            gcp_service (object): A Resource object with methods for interacting
                with the service.
            credentials (OAuth2Credentials): A Credentials object
            component (str): The subcomponent of the gcp service for this
                repository instance. E.g. 'instances' for compute.instances().*
                APIs
            num_retries (int): The number of http retriable errors to retry on
                before hard failing.
            key_field (str): The field name representing the project to
                query in the API.
            entity_field (str): The API entity returned generally by the .get()
                api. E.g. 'instance' for compute.instances().get()
            list_key_field (str): Optional override of key field for calls to
                list methods.
            get_key_field (str): Optional override of key field for calls to
                get methods.
            max_results_field (str): The field name that represents the maximum
                number of results to return in one page.
            search_query_field (str): The field name used to filter search
                results.
            rate_limiter (object): A RateLimiter object to manage API quota.
            use_cached_http (bool): If set to true, calls to the API will use
                a thread local shared http object. When false a new http object
                is used for each request.
        """
        self.gcp_service = gcp_service
        self._credentials = credentials
        self._component = None

        if component:
            component_api = gcp_service
            for c in component.split('.'):
                component_api = getattr(component_api, c)
            self._component = component_api()

        self._entity_field = entity_field
        self._num_retries = num_retries
        if list_key_field:
            self._list_key_field = list_key_field
        else:
            self._list_key_field = key_field
        if get_key_field:
            self._get_key_field = get_key_field
        else:
            self._get_key_field = key_field
        self._max_results_field = max_results_field
        self._search_query_field = search_query_field
        self._rate_limiter = rate_limiter

        self._use_cached_http = use_cached_http
        self._local = LOCAL_THREAD

    @property
    def http(self):
        """A thread local instance of httplib2.Http.

        Returns:
            httplib2.Http: An Http instance authorized by the credentials.
        """
        if self._use_cached_http and hasattr(self._local, 'http'):
            return self._local.http

        http = httplib2.Http(timeout=HTTP_REQUEST_TIMEOUT)
        self._credentials.authorize(http=http)
        if self._use_cached_http:
            self._local.http = http
        return http

    def _build_request(self, verb, verb_arguments):
        """Builds HttpRequest object.

        Args:
            verb (str): Request verb (ex. insert, update, delete).
            verb_arguments (dict): Arguments to be passed with the request.

        Returns:
            httplib2.HttpRequest: HttpRequest to be sent to the API.
        """
        method = getattr(self._component, verb)

        # Python insists that keys in **kwargs be strings (not variables).
        # Since we initially build our kwargs as a dictionary where one of the
        # keys is a variable (target), we need to convert keys to strings,
        # even though the variable in question is of type str.
        method_args = {str(k): v for k, v in verb_arguments.iteritems()}
        return method(**method_args)

    def _build_next_request(self, verb, prior_request, prior_response):
        """Builds pagination-aware request object.

        More details:
          https://developers.google.com/api-client-library/python/guide/pagination

        Args:
            verb (str): Request verb (ex. insert, update, delete).
            prior_request (httplib2.HttpRequest): Request that may trigger
                paging.
            prior_response (dict): Potentially partial response.

        Returns:
            httplib2.HttpRequest: HttpRequest or None. None is returned when
                there is nothing more to fetch - request completed.
        """
        method = getattr(self._component, verb + '_next')
        return method(prior_request, prior_response)

    def supports_pagination(self, verb):
        """Determines if the API action supports pagination.

        Args:
            verb (str): Request verb (ex. insert, update, delete).

        Returns:
            bool: True when API supports pagination, False otherwise.
        """
        return getattr(self._component, verb + '_next', None)

    def execute_command(self, verb, verb_arguments):
        """Executes command (ex. add) via a dedicated http object.

        Async APIs may take minutes to complete. Therefore, callers are
        encouraged to leverage concurrent.futures (or similar) to place long
        running commands on a separate threads.

        Args:
            verb (str): Method to execute on the component (ex. get, list).
            verb_arguments (dict): key-value pairs to be passed to
                _build_request.

        Returns:
            dict: An async operation Service Response.
        """
        request = self._build_request(verb, verb_arguments)
        return self._execute(request)

    def execute_paged_query(self, verb, verb_arguments):
        """Executes query (ex. list) via a dedicated http object.

        Args:
            verb (str): Method to execute on the component (ex. get, list).
            verb_arguments (dict): key-value pairs to be passed to
                _BuildRequest.

        Yields:
            dict: Service Response.

        Raises:
            PaginationNotSupportedError: When an API does not support paging.
        """
        if not self.supports_pagination(verb=verb):
            raise PaginationNotSupported('{} does not support pagination')

        request = self._build_request(verb, verb_arguments)

        number_of_pages_processed = 0
        while request is not None:
            response = self._execute(request)
            number_of_pages_processed += 1
            log.debug('Executing paged request #%s', number_of_pages_processed)
            request = self._build_next_request(verb, request, response)
            yield response

    def execute_search_query(self, verb, verb_arguments):
        """Executes query (ex. search) via a dedicated http object.

        Args:
            verb (str): Method to execute on the component (ex. search).
            verb_arguments (dict): key-value pairs to be passed to
                _BuildRequest.

        Yields:
            dict: Service Response.
        """
        # Implementation of search does not follow the standard API pattern.
        # Fields need to be in the body rather than sent seperately.
        next_page_token = None
        number_of_pages_processed = 0
        while True:
            req_body = verb_arguments.get('body', dict())
            if next_page_token:
                req_body['pageToken'] = next_page_token
            request = self._build_request(verb, verb_arguments)
            response = self._execute(request)
            number_of_pages_processed += 1
            log.debug('Executing paged request #%s', number_of_pages_processed)
            next_page_token = response.get('nextPageToken')
            yield response

            if not next_page_token:
                break

    def execute_query(self, verb, verb_arguments):
        """Executes query (ex. get) via a dedicated http object.

        Args:
            verb (str): Method to execute on the component (ex. get, list).
            verb_arguments (dict): key-value pairs to be passed to
                _BuildRequest.

        Returns:
            dict: Service Response.
        """
        request = self._build_request(verb, verb_arguments)
        return self._execute(request)

    @retry(retry_on_exception=is_retryable_exception,
           wait_exponential_multiplier=1000,
           wait_exponential_max=10000,
           stop_max_attempt_number=5)
    def _execute(self, request):
        """Run execute with retries and rate limiting.

        Args:
            request (object): The HttpRequest object to execute.

        Returns:
            dict: The response from the API.
        """
        if self._rate_limiter:
            # Since the ratelimiter library only exposes a context manager
            # interface the code has to be duplicated to handle the case where
            # no rate limiter is defined.
            with self._rate_limiter:
                return request.execute(http=self.http,
                                       num_retries=self._num_retries)
        return request.execute(http=self.http,
                               num_retries=self._num_retries)
