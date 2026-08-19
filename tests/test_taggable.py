# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import itertools
import logging
import pytest

from c7n.exceptions import PolicyValidationError

from .zpill import ACCOUNT_ID


def test_taggable_query_schema_error(test):
    with pytest.raises(PolicyValidationError) as excinfo:
        test.load_policy({"name": "xyz", "resource": "aws.taggable"})

    assert "requires the use of a `query`" in str(excinfo.value)

    with pytest.raises(PolicyValidationError) as excinfo:
        test.load_policy({
            "name": "xyz", "resource": "aws.taggable",
            "query": [{"non_compliant": 123}]
        })

    assert "not valid under any of the given schemas" in str(excinfo.value)


def test_taggable_check_policy(test, caplog):
    factory = test.replay_flight_data("test_taggable_check_policy_tags")
    policy = test.load_policy({
        "name": "test-taggable-check",
        "resource": "aws.taggable",
        "query": [
            {"non_compliant": True},
            {"check_policy_tags": ["AppEnv"]},
            {"resource_types": ["ec2:security-group"]},

        ]},
        session_factory=factory
    )
    assert policy.run() == []
    assert "policy tags dont match organization" in caplog.text
    assert "CRITICAL" in caplog.text
    print(caplog.text)


def test_taggable_bad_explorer_index(test, caplog):
    factory = test.replay_flight_data("test_taggable_bad_explorer_index", region="eu-west-1")
    policy = test.load_policy({
        "name": "test-taggable-check",
        "resource": "aws.taggable",
        "query": [
            {"non_compliant": True},
            {"non_tagged": True},
            {"resource_types": ["ec2:security-group"]},
        ]},
        session_factory=factory,
        config={'account_id': ACCOUNT_ID, 'region': 'eu-west-1'}
    )

    caplog.set_level(logging.CRITICAL)
    policy.run()
    assert "misconfigured default view" in caplog.text
    assert "CRITICAL" in caplog.text
    assert "account:%s region:eu-west-1" % ACCOUNT_ID in caplog.text


def test_taggable_noncompliant(test):
    factory = test.replay_flight_data("test_taggable_fetch")

    policy = test.load_policy(
        {"name": "test-taggable-fetch",
         "resource": "aws.taggable",
         "query": [
             {"non_compliant": True},
             {"non_tagged": True},
             {"resource_types": ["ec2:security-group"]},
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
