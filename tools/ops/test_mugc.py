# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from botocore.exceptions import ClientError

import mugc

from c7n import mu


class Options:

    prefix = "custodian-"
    policy_regex = "^custodian-.*"
    present = False
    dryrun = False


class PolicyConfig:

    assume_role = None
    profile = None
    external_id = None


def test_region_gc_schedule_mode_function():
    """Schedule-mode policy lambdas are garbage collected without error.

    Regression test for #10312: an EventBridge schedule mode function has an
    empty resource policy, so ``get_policy`` raises ResourceNotFoundException
    and mugc falls back to reading the ``custodian-schedule`` tag from the
    ``get_function`` response.
    """
    function_name = "custodian-test-app-mypolicy"

    lambda_client = mock.MagicMock()
    lambda_client.get_policy.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "GetPolicy")
    lambda_client.get_function.return_value = {
        "Tags": {"custodian-schedule": "name=custodian-test-app-mypolicy:group=mygroup"}
    }

    manager = mock.MagicMock()
    manager.list_functions.return_value = [{
        "FunctionName": function_name,
        "Role": "arn:aws:iam::644160558196:role/mypolicy",
        "Handler": "custodian_policy.run",
        "Timeout": 900,
        "MemorySize": 512,
        "Description": "",
        "Runtime": "python3.11",
    }]

    session_factory = mock.MagicMock()
    session_factory.return_value.client.return_value = lambda_client

    with mock.patch.object(mugc, "SessionFactory", return_value=session_factory), \
            mock.patch.object(mugc.mu, "LambdaManager", return_value=manager):
        mugc.region_gc(Options(), "us-east-1", PolicyConfig(), [])

    manager.remove.assert_called_once()
    removed = manager.remove.call_args.args[0]
    assert removed.func_data["name"] == function_name
    events = removed.func_data["events"]
    assert len(events) == 1
    assert isinstance(events[0], mu.EventBridgeScheduleSource)
    assert events[0].data == {"group-name": "mygroup"}
