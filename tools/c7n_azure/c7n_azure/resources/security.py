# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib
import inspect
import logging
import time
import types
from collections.abc import Iterator
from functools import lru_cache

from c7n.exceptions import PolicyExecutionError
from c7n.utils import local_session
from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager
from c7n_azure.query import TypeInfo
from c7n_azure.session import Session
from c7n_azure.utils import StringUtils

send_logger = logging.getLogger('custodian.azure.resources.security.SecurityPricing.get')


class AbstractSecurity(QueryResourceManager):

    def get_client(self, service=None):
        if not service:
            return self.client(
                "%s.%s" % (self.resource_type.service, self.resource_type.client))
        return self.client(service)

    @lru_cache()
    def client(self, client):
        credentials = self.get_session().get_credentials()
        subscription_id = self.get_session().get_subscription_id()
        service_name, client_name = client.rsplit('.', 1)
        svc_module = importlib.import_module(service_name)
        klass = getattr(svc_module, client_name)

        klass_parameters = inspect.signature(klass).parameters

        if 'subscription_id' in klass_parameters:
            client = klass(credential=credentials, asc_location='', subscription_id=subscription_id)
        else:
            client = klass(credential=credentials, asc_location='')

        service_client = client._client._pipeline
        service_client.orig_run = service_client.run
        service_client.run = types.MethodType(custodian_azure_get_override, service_client)

        return client


def custodian_azure_get_override(self, *args, **kwargs):
    """ Overrides ServiceClient.send() function to implement retries & log headers
    """
    retries = 0
    max_retries = 3
    while retries < max_retries:
        pipeline_response = self.orig_run(*args, **kwargs)
        response = pipeline_response.http_response
        send_logger.debug(response.status_code)
        for k, v in response.headers.items():
            if k.startswith('x-ms-ratelimit'):
                send_logger.debug(k + ':' + v)

        # Retry codes from urllib3/util/retry.py
        if response.status_code in [413, 429, 503]:
            retry_after = None
            for k in response.headers.keys():
                if StringUtils.equal('retry-after', k):
                    retry_after = int(response.headers[k])

            if retry_after is not None and retry_after < constants.DEFAULT_MAX_RETRY_AFTER:
                send_logger.warning('Received retriable error code %i. Retry-After: %i'
                                    % (response.status_code, retry_after))
                time.sleep(retry_after)
                retries += 1
            else:
                send_logger.error("Received throttling error, retry time is %i"
                                  "(retry only if < %i seconds)."
                                  % (retry_after or 0, constants.DEFAULT_MAX_RETRY_AFTER))
                break
        else:
            break
    return pipeline_response


@resources.register('security-assessments')
class SecurityAssessments(AbstractSecurity):
    class resource_type(TypeInfo):
        class SubscriptionIdIterator(Iterator):
            def __next__(self):
                if hasattr(self, 'returned'):
                    raise StopIteration
                setattr(self, 'returned', True)
                subscription_id = local_session(Session).get_subscription_id()
                if not subscription_id:
                    raise PolicyExecutionError(
                        "Unknown subscription, try setting AZURE_SUBSCRIPTION_ID")
                return 'scope', f'/subscriptions/{subscription_id}'

        doc_groups = ['Security']
        service = 'azure.mgmt.security'
        client = 'SecurityCenter'
        enum_spec = ('assessments', 'list', SubscriptionIdIterator())
        resource_type = 'Microsoft.Security/assessments'
        default_report_fields = ["id", "name"]