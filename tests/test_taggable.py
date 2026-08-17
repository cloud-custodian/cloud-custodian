# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import itertools

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


def test_taggable_tag_action(test):
    factory = test.replay_flight_data("test_taggable_tag_action")

    policy = test.load_policy(
        {"name": "test-taggable-fetch",
         "resource": "aws.taggable",
         "actions": [
             {"type": "tag",
              "key": "NonCompliant",
              "value": "FOUND"}
         ],
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

    client = factory().client('resourcegroupstaggingapi')
    post_resources = client.get_resources(
        ResourceARNList=[r['ResourceARN'] for r in resources]
    )['ResourceTagMappingList']

    pre_tags = {t['Key'] for t in itertools.chain.from_iterable([r['Tags'] for r in resources])}
    post_tags = {t['Key'] for t in
                 itertools.chain.from_iterable([r['Tags'] for r in post_resources])}
    assert post_tags - pre_tags == {"NonCompliant"}
