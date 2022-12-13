# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

import jmespath


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
        default_report_fields = ['id', 'displayName']
        asset_type = "cloudbilling.googleapis.com/BillingAccount"
        permissions = ('billing.accounts.list',)
        urn_component = "account"

        @staticmethod
        def get(client, event):
            return client.execute_query(
                'get', {'name': jmespath.search(
                    'protoPayload.response.billingAccountInfo.billingAccountName', event)})

        @classmethod
        def _get_id(cls, resource):
            # Billing name contains the component element too.
            id = resource[cls.id]
            return id.split('/',1)[-1]
