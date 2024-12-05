# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform


@terraform("quicksight_group")
def test_quicksight_group_query(test, quicksight_group):
    factory = test.replay_flight_data("test_quicksight_group_query")

    policy = test.load_policy({
      "name": "test-aws-quicksight-group",
      "resource": "aws.quicksight-group"
    }, session_factory=factory, config={'account_id': '490065885863'})

    resources = policy.run()
    assert len(resources) > 0
    assert resources[0]['GroupName'] == 'tf-example'
