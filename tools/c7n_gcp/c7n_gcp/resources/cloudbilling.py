# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n.utils import jmespath_search


@resources.register('cloudbilling-account')
class CloudBillingAccount(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudbilling'
        version = 'v1'
        component = 'billingAccounts'
        enum_spec = ('list', 'billingAccounts[]', None)
        get_requires_event = True
        scope = None
        name = id = 'name'
        default_report_fields = ['name', 'displayName']
        asset_type = "cloudbilling.googleapis.com/BillingAccount"
        permissions = ('billing.accounts.list',)
        urn_component = "account"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': jmespath_search(
                    'protoPayload.response.billingAccountInfo.billingAccountName', event)})
