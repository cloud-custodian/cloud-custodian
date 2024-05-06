# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from pytest_terraform import terraform


def test_delete(test_awscc):
    factory = test_awscc.replay_flight_data("awscc_log_delete")
    p = test_awscc.load_policy(
        {
            "name": "log-del",
            "resource": "awscc.logs_loggroup",
            "filters": [{"LogGroupName": "/aws/apigateway/welcome"}],
            "actions": ["delete"],
        },
        session_factory=factory,
    )

    resources = p.run()
    assert len(resources) == 1

    if test_awscc.recording:
        time.sleep(2)

    client = factory().client("logs")
    assert (
        client.describe_log_groups(logGroupNamePrefix="/aws/apigateway/welcome").get("logGroups")
        == []
    )


@terraform("aws_athena_workgroup", replay=True)
def test_update_workgroup(test_awscc, aws_athena_workgroup):
    factory = test_awscc.replay_flight_data("awscc_workgroup_update")
    p = test_awscc.load_policy(
        {
            "name": "work-up",
            "resource": "awscc.athena_workgroup",
            "filters": [{"Name": aws_athena_workgroup["aws_athena_workgroup.example.name"]}],
            "actions": [
                {
                    "type": "update",
                    "patch": [
                        dict(
                            op="add",
                            path="/WorkGroupConfiguration/EnforceWorkGroupConfiguration",
                            value=False,
                        ),
                        dict(
                            op="add",
                            path="/WorkGroupConfiguration/ResultConfiguration",
                            value={"EncryptionConfiguration": {"EncryptionOption": "SSE_S3"}},
                        ),
                    ],
                }
            ],
        },
        session_factory=factory,
    )

    resources = p.run()
    assert len(resources) == 1
    client = factory().client('athena')
    if test_awscc.recording:
        time.sleep(4)

    wg = client.get_work_group(
        WorkGroup=aws_athena_workgroup["aws_athena_workgroup.example.name"]
    ).get("WorkGroup")
    assert wg["Configuration"]["EnforceWorkGroupConfiguration"] is False
    assert (
        wg["Configuration"]["ResultConfiguration"]["EncryptionConfiguration"]["EncryptionOption"]
        == "SSE_S3"
    )


def test_update(test_awscc):
    factory = test_awscc.replay_flight_data("awscc_log_update")
    group_name = "/aws/codebuild/custodian-build-python"
    p = test_awscc.load_policy(
        {
            "name": "log-up",
            "resource": "awscc.logs_loggroup",
            "filters": [{"LogGroupName": group_name}],
            "actions": [
                {
                    "type": "update",
                    "RetentionInDays": 7,
                    "Tags": [{"Key": "Owner", "Value": "Kapil"}],
                }
            ],
        },
        session_factory=factory,
    )

    resources = p.run()
    assert len(resources) == 1
    assert "RetentionInDays" not in resources[0]
    assert "Tags" not in resources[0]

    if test_awscc.recording:
        time.sleep(2)

    updated = p.resource_manager.get_resources([group_name])

    assert updated[0] == {
        "Arn": (
            "arn:aws:logs:us-east-1:644160558196:"
            "log-group:/aws/codebuild/custodian-build-python:*"
        ),
        "LogGroupName": "/aws/codebuild/custodian-build-python",
        "RetentionInDays": 7,
        "Tags": [{"Key": "Owner", "Value": "Kapil"}],
    }
