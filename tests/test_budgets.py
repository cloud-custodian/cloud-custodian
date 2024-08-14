# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform

from .zpill import ACCOUNT_ID


@terraform("budgets_budget")
def test_budget_query(test, budgets_budget):
    factory = test.replay_flight_data("test_budget_query")

    policy = test.load_policy({
      "name": "test-aws-budget",
      "resource": "aws.budget"
    }, session_factory=factory, config={"account_id": ACCOUNT_ID})

    resources = policy.run()
    assert len(resources) > 0
