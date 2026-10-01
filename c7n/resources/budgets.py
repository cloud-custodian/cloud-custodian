# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.utils import local_session


class DescribeBudget(query.DescribeSource):

    def resources(self, query):
        params = {
            "AccountId": self.manager.config.account_id,
            # FilterExpression is omitted from the response unless asked for,
            # and supersedes the deprecated CostFilters.
            "ShowFilterExpression": True,
        }
        params.update(query or {})
        return super().resources(params)

    def augment(self, resources):
        resources = super().augment(resources)
        if not resources:
            return resources
        client = local_session(self.manager.session_factory).client("budgets")
        paginator = client.get_paginator("describe_budget_notifications_for_account")
        paginator.PAGE_ITERATOR_CLS = query.RetryPageIterator
        notifications = {}
        for page in paginator.paginate(AccountId=self.manager.config.account_id):
            for b in page.get("BudgetNotificationsForAccount", ()):
                notifications.setdefault(b["BudgetName"], []).extend(
                    b.get("Notifications", ()))
        for r in resources:
            r["Notifications"] = notifications.get(r["BudgetName"], [])
        return resources


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
