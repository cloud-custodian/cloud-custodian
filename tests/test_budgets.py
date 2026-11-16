# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

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
    assert len(resources) == 1
    assert resources[0]["Notifications"] == [{
        "NotificationType": "FORECASTED",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": 100.0,
        "ThresholdType": "PERCENTAGE",
        "NotificationState": "OK",
    }]
    assert resources[0]["FilterExpression"]["Dimensions"]["Key"] == "SERVICE"


def test_budget_notifications(test):
    factory = test.replay_flight_data("test_budget_notifications")

    policy = test.load_policy({
        "name": "aws-budget-notifications",
        "resource": "aws.budget",
    }, session_factory=factory, config={"account_id": ACCOUNT_ID})

    notifications = {
        r["BudgetName"]: r["Notifications"] for r in policy.run()}
    assert len(notifications["budget-ec2-alerted"]) == 2
    # a budget without notifications gets an empty collection, not a missing key
    assert notifications["budget-s3-unalerted"] == []


def test_budget_missing_actual_spend_alert(test):
    factory = test.replay_flight_data("test_budget_notifications")

    policy = test.load_policy({
        "name": "aws-budget-missing-actual-spend-alert",
        "resource": "aws.budget",
        "filters": [
            {"type": "value", "key": "BudgetType", "value": "COST"},
            {"type": "value", "key": "FilterExpression.Dimensions.Key",
             "value": "SERVICE"},
            {"or": [
                {"type": "value", "key": "AutoAdjustData.AutoAdjustType",
                 "op": "ne", "value": "HISTORICAL"},
                {"type": "value",
                 "key": "Notifications[?NotificationType=='ACTUAL'"
                        " && ComparisonOperator=='GREATER_THAN']",
                 "value": "empty"},
            ]},
        ],
    }, session_factory=factory, config={"account_id": ACCOUNT_ID})

    resources = policy.run()
    assert [r["BudgetName"] for r in resources] == ["budget-s3-unalerted"]


def test_budget_query_params_merged(test):
    factory = test.replay_flight_data("test_budget_notifications")

    policy = test.load_policy({
        "name": "aws-budget-enum",
        "resource": "aws.budget",
    }, session_factory=factory, config={"account_id": ACCOUNT_ID})

    source = policy.resource_manager.source
    captured = {}

    def record(client, enum_op, params, path, retry=None):
        captured.update(params)
        return []

    with patch.object(source.query, "_invoke_client_enum", record):
        source.resources({"MaxResults": 50})

    assert captured == {
        "AccountId": ACCOUNT_ID,
        "ShowFilterExpression": True,
        "MaxResults": 50,
    }
