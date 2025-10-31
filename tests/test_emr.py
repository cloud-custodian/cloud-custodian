# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import unittest

from c7n.exceptions import PolicyValidationError
from c7n.resources import emr
from c7n.resources.emr import actions, EMRQueryParser

from .common import BaseTest


class TestEMR(BaseTest):

    def test_get_emr_by_ids(self):
        session_factory = self.replay_flight_data("test_emr_query_ids")
        p = self.load_policy(
            {'name': 'emr', 'resource': 'aws.emr'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(["j-1EJMJNTXC63JW"])
        self.assertEqual(resources[0]["Id"], "j-1EJMJNTXC63JW")

    def test_get_emr_tags(self):
        session_factory = self.replay_flight_data("test_get_emr_tags")
        policy = self.load_policy(
            {
                "name": "test-get-emr-tags",
                "resource": "emr",
                "filters": [{"tag:first_tag": "first"}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        cluster = session_factory().client("emr").describe_cluster(
            ClusterId="j-1U3KBYP5TY79M"
        )
        cluster_tags = cluster["Cluster"]["Tags"]
        tags = {t["Key"]: t["Value"] for t in cluster_tags}
        self.assertEqual(tags["first_tag"], "first")

    def test_emr_mark(self):
        session_factory = self.replay_flight_data("test_emr_mark")
        p = self.load_policy(
            {
                "name": "emr-mark",
                "resource": "emr",
                "filters": [{"tag:first_tag": "first"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "days": 4,
                        "op": "terminate",
                        "tag": "test_tag",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        new_tags = resources[0]["Tags"]
        self.assertEqual(len(resources), 1)
        tag_map = {t["Key"]: t["Value"] for t in new_tags}
        self.assertTrue("test_tag" in tag_map)

    def test_emr_tag(self):
        session_factory = self.replay_flight_data("test_emr_tag")
        p = self.load_policy(
            {
                "name": "emr-tag-table",
                "resource": "emr",
                "filters": [{"tag:first_tag": "first"}],
                "actions": [{"type": "tag", "tags": {"new_tag_key": "new_tag_value"}}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        new_tags = resources[0]["Tags"]
        tag_map = {t["Key"]: t["Value"] for t in new_tags}
        self.assertEqual(
            {
                "first_tag": "first",
                "second_tag": "second",
                "new_tag_key": "new_tag_value",
            },
            tag_map,
        )

    def test_emr_unmark(self):
        session_factory = self.replay_flight_data("test_emr_unmark")
        p = self.load_policy(
            {
                "name": "emr-unmark",
                "resource": "emr",
                "filters": [{"tag:first_tag": "first"}],
                "actions": [{"type": "remove-tag", "tags": ["test_tag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        old_tags = resources[0]["Tags"]
        self.assertEqual(len(resources), 1)
        self.assertFalse("test_tag" in old_tags)

    def test_emr_sg(self):
        session_factory = self.replay_flight_data("test_emr_sg")
        p = self.load_policy(
            {
                "name": "emr-sg-tag",
                "resource": "emr",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:NetworkLocation",
                        "value": "CustFacing,EntFacing"
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "pratyush-emr-test")

    def test_emr_security_configuration(self):
        session_factory = self.replay_flight_data("test_emr_sc")
        p = self.load_policy(
            {
                "name": "emr-sc-filter",
                "resource": "emr",
                "filters": [
                    {
                        "type": "security-configuration",
                        "key": "EncryptionConfiguration.EnableAtRestEncryption",
                        "value": True
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["c7n:SecurityConfiguration"],
            {'EncryptionConfiguration': {
                'AtRestEncryptionConfiguration': {
                    'S3EncryptionConfiguration': {
                        'EncryptionMode': 'SSE-S3'}},
                'EnableAtRestEncryption': True,
                'EnableInTransitEncryption': False}})


class TestEMRQueryParser(unittest.TestCase):
    def test_query(self):
        self.assertEqual(EMRQueryParser.parse([]), [])

        query = [{'ClusterStates': 'RUNNING'}, {'CreatedBefore': '2022-02-23'}]
        result_query = [{'ClusterStates': ['RUNNING']}, {'CreatedBefore': '2022-02-23'}]
        self.assertEqual(EMRQueryParser.parse(query), result_query)

        query = [{'ClusterStates': ['RUNNING', 'WAITING']}]
        self.assertEqual(EMRQueryParser.parse(query), query)

        query = [{"CreatedBefore": 1470968567.05}]
        self.assertEqual(EMRQueryParser.parse(query), query)

        query = [{"CreatedAfter": '2022-09-15T17:15:20.000Z'}]
        self.assertEqual(EMRQueryParser.parse(query), query)

        query = [{'ClusterStates': 'RUNNING'}, {'ClusterStates': 'WAITING'}]
        result_query = [{'ClusterStates': ['RUNNING', 'WAITING']}]
        self.assertEqual(EMRQueryParser.parse(query), result_query)

    def test_invalid_query(self):
        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [{"tag:Test": "True"}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [{"foo": "bar"}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [{"tag:ASV": None}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [
            {"too": "many", "keys": "error"}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, ["Not a dictionary"])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [
            {"CreatedBefore": '2022-02-23'}, {"CreatedBefore": '2022-02-24'}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [
            {"CreatedBefore": ['2022-02-23']}])

        self.assertRaises(PolicyValidationError, EMRQueryParser.parse, [
            {"CreatedBefore": '2022-02-23'}, ["not a dict"]])


class TestTerminate(BaseTest):

    def test_emr_terminate(self):
        session_factory = self.replay_flight_data("test_emr_terminate")
        policy = self.load_policy(
            {
                "name": "emr-test-terminate",
                "resource": "emr",
                "actions": [{"type": "terminate"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestActions(unittest.TestCase):

    def test_action_construction(self):

        self.assertIsInstance(actions.factory("terminate", None), emr.Terminate)


class TestEMRSecurityConfiguration(BaseTest):
    def test_emr_security_configuration(self):
        session_factory = self.replay_flight_data("test_emr_security_configuration")
        p = self.load_policy(
            {
                'name': 'emr',
                'resource': 'emr-security-configuration',
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(resources[0]["SecurityConfiguration"]['EncryptionConfiguration']
             ['EnableInTransitEncryption'], False)

    def test_emr_security_configuration_delete(self):
        session_factory = self.replay_flight_data("test_emr_security_configuration_delete")
        p = self.load_policy(
            {
                'name': 'emr',
                'resource': 'emr-security-configuration',
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory(region="us-east-1").client("emr")
        resp = client.list_security_configurations()
        self.assertFalse(
            resp['SecurityConfigurations']
        )


class TestEMRServerless(BaseTest):
    def test_emr_serverless_tag(self):
        session_factory = self.replay_flight_data("test_emr_serverless_tag")
        p = self.load_policy(
            {
                "name": "emr-serverless-tag",
                "resource": "aws.emr-serverless-app",
                "filters": [{"tag:foo": "absent"}],
                "actions": [{"type": "tag", "tags": {"foo": "bar"}}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("emr-serverless")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])["tags"]
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {"foo": "bar"})

    def test_emr_serverless_remove_tag(self):
        session_factory = self.replay_flight_data("test_emr_serverless_remove_tag")
        p = self.load_policy(
            {
                'name': "test-emr-serverless-tag",
                'resource': "aws.emr-serverless-app",
                'filters': [{'tag:foo': 'present'}],
                'actions': [{'type': 'remove-tag', 'tags': ['foo']}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("emr-serverless")
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])["tags"]
        self.assertEqual(len(tags), 0)

    def test_emr_serverless_delete(self):
        session_factory = self.replay_flight_data('test_emr_serverless_delete')
        p = self.load_policy(
            {
                'name': 'test-emr-serverless-delete',
                'resource': 'aws.emr-serverless-app',
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('emr-serverless')
        applications = client.list_applications()['applications']
        self.assertEqual(len(applications), 0)

    def test_emr_serverless_markop(self):
        session_factory = self.replay_flight_data("test_emr_serverless_markop")
        p = self.load_policy(
            {
                "name": "emr-serverless-markop",
                "resource": "aws.emr-serverless-app",
                "filters": [{"tag:foo": "absent"}],
                "actions": [{"type": "mark-for-op", "op": "notify", "tag": "foo", "days": 2}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('emr-serverless')
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'foo': 'Resource does not meet policy: notify@2023/01/26'})
