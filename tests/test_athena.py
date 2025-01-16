# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform
from .zpill import ACCOUNT_ID


def test_athena_catalog(test):
    factory = test.replay_flight_data("test_athena_data_catalog")
    policy = test.load_policy(
        {"name": "test-athena-catallog",
         "resource": "aws.athena-data-catalog",
         },
        session_factory=factory
    )
    resources = policy.run()
    assert len(resources) == 2


@terraform("athena_workgroup")
def test_athena_work_group(test, athena_workgroup):
    factory = test.replay_flight_data("test_athena_work_group")
    policy = test.load_policy(
        {"name": "test-athena-work-group",
         "resource": "aws.athena-work-group",
         "filters": [{"Name": athena_workgroup["aws_athena_workgroup.working.name"]}]
         },
        config={'account_id': ACCOUNT_ID},
        session_factory=factory
    )

    resources = policy.run()
    assert len(resources) == 1
    tag_map = {t['Key']: t['Value'] for t in resources[0]['Tags']}
    assert tag_map == {
        'App': 'c7n-test',
        'Env': 'Dev',
        'Name': 'something'
    }


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
