# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('savings-plan')
class SavingsPlan(QueryResourceManager):
    """AWS SavingsPlans resource.

    Query savings plans for an AWS account.

    :example:

    .. code-block:: yaml

        policies:
          - name: savings-plans-query
            resource: savings-plan
    """

    class resource_type(TypeInfo):
        service = 'savingsplans'
        arn_type = 'savingsplan'
        enum_spec = ('describe_savings_plans', 'SavingsPlans', None)
        id = 'SavingsPlanId'
        name = 'SavingsPlanId'
        config_id = 'savingsPlanId'
        universal_taggable = True
        # SavingsPlans are global resources
        global_resource = True
        cfn_type = 'AWS::SavingsPlans::SavingsPlans'
        permissions_augment = ("savingsplans:DescribeSavingsPlans",)
