# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .zpill import ACCOUNT_ID


def test_taggable_noncompliant(test):
    factory = test.replay_flight_data("test_taggable_fetch")

    policy = test.load_policy(
        {"name": "test-taggable-fetch",
         "resource": "aws.taggable",
         "query": [
             {"non_compliant": True},
             {"non_tagged": True},
             {"resource_types": ["ec2:security-group"]},
             {"check_policy_tags": ["Owner"]}
         ]},
        session_factory=factory,
        config={"account_id": ACCOUNT_ID},

    )

    resources = policy.run()
    assert len(resources) == 16


def test_taggable_tagmatch(test):
    factory = test.replay_flight_data("test_taggable_tagmatch_fetch")

    policy = test.load_policy(
        {"name": "test-taggable-fetch",
         "resource": "aws.taggable",
         "query": [
             {"non_compliant": True},
             {"non_tagged": True},
             {"with_tags": [{"Key": "kubernetes.io/cluster/app-dev", "Values": ["owned"]}]},
             {"resource_types": ["ec2:security-group"]},
             {"check_policy_tags": ["Owner"]}
         ]},
        session_factory=factory,
        config={"account_id": ACCOUNT_ID}
    )
    resources = policy.run()
    assert len(resources) == 3
