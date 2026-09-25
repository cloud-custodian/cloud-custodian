# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import ChildResourceManager, ChildTypeInfo


@resources.register('billing-budget')
class BillingBudget(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/billing/docs/reference/budget/rest/v1/billingAccounts.budgets

    Example::

        policies:
          - name: gcp-billing-budget-no-last-period-amount
            resource: gcp.billing-budget
            filters:
              - type: value
                key: amount.lastPeriodAmount
                value: absent
              - type: value
                key: budgetFilter.services
                op: contains
                value: services/C7E2-9256-1C43

    """

    class resource_type(ChildTypeInfo):
        service = 'billingbudgets'
        version = 'v1'
        component = 'billingAccounts.budgets'
        enum_spec = ('list', 'budgets[]', None)
        scope = None
        name = id = 'name'
        default_report_fields = ['name', 'displayName']
        parent_spec = {
            'resource': 'cloudbilling-account',
            'child_enum_params': [
                ('name', 'parent'),
            ],
            'parent_get_params': [
                ('name', 'name', 'regex', r'(billingAccounts/[^/]+)/'),
            ],
        }
        asset_type = "billingbudgets.googleapis.com/Budget"
        permissions = ('billing.budgets.list',)
        urn_component = "budget"
        urn_id_segments = (-1,)
