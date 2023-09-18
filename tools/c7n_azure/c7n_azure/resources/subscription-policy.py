# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser

@resources.register('subscription-policy')
class SubscriptionPolicy(ChildArmResourceManager):
    """Subscription Policy Resource

    :example:

    Returns the policy for the subscription

    .. code-block:: yaml

        policies:
          - name: subscription-tenant-policy
            resource: azure.subscription-policy
            filters:
              - type: value
                key: blockSubscriptionsIntoTenant
                value: true

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Subscription']

        service = 'azure.mgmt.subscription'
        client = 'SubscriptionClient'
        enum_spec = ('subscription_policy', 'get_policy_for_tenant', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Subscription/policies'
        parent_manager_name = 'subscription'

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'subscriptionId': parent_resource['subscriptionId']
            }
