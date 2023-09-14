# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform


@terraform("athena_named_query")
def test_athena_named_query(test, athena_named_query):
    factory = test.replay_flight_data("test_athena_named_query")

    policy = test.load_policy(
        {"name": "test-aws-athena-named-query", "resource": "aws.athena-named-query"},
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) > 0
    assert resources[0]['Database'] == athena_named_query['aws_athena_named_query.foo.database']
