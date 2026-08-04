# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from pytest_terraform import terraform
from .zpill import ACCOUNT_ID

from c7n import query as c7n_query


def test_athena_catalog_tagging(test):
    factory = test.replay_flight_data("test_athena_data_catalog_tagging")
    policy = test.load_policy(
        {
            "name": "test-athena-catalog-tagging",
            "resource": "aws.athena-data-catalog",
            "filters": [
                {
                    "CatalogName": "c7n-test"
                }
            ],
            "actions": [
                {
                    "type": "tag",
                    "key": "c7n",
                    "value": "test",
                }
            ]
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory,
    )
    resources = policy.run()
    assert len(resources) == 1

    policy = test.load_policy(
        {
            "name": "test-athena-catalog-tagging",
            "resource": "aws.athena-data-catalog",
            "filters": [
                {
                    "tag:c7n": "test"
                }
            ],
            "actions": [
                {
                    "type": "remove-tag",
                    "tags": ["c7n"]
                }
            ]
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory,
    )
    resources = policy.run()
    assert len(resources) == 1
    client = factory().client("athena")
    arn = f"arn:aws:athena:us-east-1:{ACCOUNT_ID}:datacatalog/{resources[0]['CatalogName']}"
    tags = client.list_tags_for_resource(ResourceARN=arn)["Tags"]
    assert len(tags) == 0


def test_athena_catalog_skips_aws_data_catalog(test):
    factory = test.replay_flight_data("test_athena_data_catalog_aws_catalog_skip")
    policy = test.load_policy(
        {
            "name": "test-athena-catalog-skip-aws-managed",
            "resource": "aws.athena-data-catalog",
            "actions": [
                {
                    "type": "tag",
                    "key": "c7n",
                    "value": "test",
                }
            ],
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory,
    )
    resources = policy.run()
    # AwsDataCatalog is AWS-managed; augment filters it before the tag action
    # so the tag action runs against zero resources (no ParamValidationError).
    assert len(resources) == 0


def test_athena_catalog_source_get_resources_filters_aws_managed(test):
    p = test.load_policy(
        {"name": "test-catalog-get-res", "resource": "aws.athena-data-catalog"},
        config={"account_id": ACCOUNT_ID},
    )
    source = p.resource_manager.get_source("describe")
    raw = [
        {"CatalogName": "AwsDataCatalog", "Type": "GLUE", "Tags": []},
        {"CatalogName": "user-catalog", "Type": "HIVE", "Tags": []},
    ]
    with mock.patch.object(c7n_query.DescribeWithResourceTags, "get_resources",
                           return_value=raw):
        results = source.get_resources(["AwsDataCatalog", "user-catalog"])
    assert len(results) == 1
    assert results[0]["CatalogName"] == "user-catalog"


def test_athena_catalog_tag_action_skips_empty_arns(test):
    p = test.load_policy(
        {
            "name": "test-tag-empty-arns",
            "resource": "aws.athena-data-catalog",
            "actions": [{"type": "tag", "key": "c7n", "value": "test"}],
        },
        config={"account_id": ACCOUNT_ID},
    )
    action = p.resource_manager.actions[0]
    mock_client = mock.MagicMock()
    resource = {"CatalogName": "some-catalog", "Type": "HIVE", "Tags": []}
    with mock.patch.object(p.resource_manager, "get_arns", return_value=[]):
        action.process_resource_set(mock_client, [resource], {"c7n": "test"})
    mock_client.tag_resources.assert_not_called()


def test_athena_cancel_capacity_reservation(test):
    factory = test.replay_flight_data("test_athena_cancel_capacity_reservation")
    policy = test.load_policy(
        {
            "name": "delete-cap-reserve",
            "resource": "aws.athena-capacity-reservation",
            "filters": [{"Name": "testv"}],
            "actions": [{"type": "cancel"}]
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory
    )

    resources = policy.run()
    assert len(resources) == 1
    assert len(resources[0]['Tags']) == 3

    cap = (
        factory().client("athena").get_capacity_reservation(Name="testv").get("CapacityReservation")
    )
    assert cap["Status"] != "ACTIVE"


def test_athena_work_group_update(test):
    factory = test.replay_flight_data("test_athena_work_group_update")
    policy = test.load_policy(
        {
            "name": "update-workgroup",
            "resource": "aws.athena-work-group",
            "filters": [{"Name": "primary"}],
            "actions": [{"type": "update", "config": {"PublishCloudWatchMetricsEnabled": True}}],
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory,
    )
    policy.run()
    wg = factory().client("athena").get_work_group(WorkGroup="primary").get("WorkGroup")
    assert wg["Configuration"]["PublishCloudWatchMetricsEnabled"] is True


@terraform("athena_workgroup")
def test_athena_work_group(test, athena_workgroup):
    factory = test.replay_flight_data("test_athena_work_group")
    policy = test.load_policy(
        {
            "name": "test-athena-work-group",
            "resource": "aws.athena-work-group",
            "filters": [{"Name": athena_workgroup["aws_athena_workgroup.working.name"]}],
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    tag_map = {t["Key"]: t["Value"] for t in resources[0]["Tags"]}
    assert tag_map == {"App": "c7n-test", "Env": "Dev", "Name": "something"}


@terraform("athena_named_query")
def test_athena_named_query(test, athena_named_query):
    factory = test.replay_flight_data("test_athena_named_query")

    policy = test.load_policy(
        {"name": "test-aws-athena-named-query", "resource": "aws.athena-named-query"},
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) > 0
    assert resources[0]["Database"] == athena_named_query["aws_athena_named_query.foo.database"]
