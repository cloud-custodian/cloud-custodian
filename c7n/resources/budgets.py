# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


class DescribeBudget(query.DescribeSource):
    def resources(self, query):
        required = {"AccountId": self.manager.config.account_id}
        return super().resources(required)


@resources.register("budget")
class Budget(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "budgets"
        enum_spec = ('describe_budgets', 'Budgets', None)
        global_resource = True
        arn_type = "budget"
        id = "BudgetName"
        name = "BudgetName"
        cfn_type = "AWS::Budgets::Budget"
        permissions_enum = ["budgets:ViewBudget"]

    source_mapping = {
        "describe": DescribeBudget,
    }
