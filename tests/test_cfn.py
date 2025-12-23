# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import time
from unittest.mock import MagicMock, patch

import yaml

from c7n.resources.cfn import CloudFormationAddTag, CloudFormationRemoveTag
from .common import BaseTest


class TestCFN(BaseTest):
    def test_delete(self):
        factory = self.replay_flight_data("test_cfn_delete")
        p = self.load_policy(
            {
                "name": "cfn-delete",
                "resource": "cfn",
                "filters": [{"StackStatus": "ROLLBACK_COMPLETE"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.maxDiff = None
        self.assertEqual(
            sorted([r["StackName"] for r in resources]),
            ["sphere11-db-1", "sphere11-db-2", "sphere11-db-3"],
        )

    def test_delete_with_protection(self):
        stack_name = "c7n-test-delete-with-protection"

        factory = self.replay_flight_data("test_cfn_delete_with_protection")
        client = factory().client("cloudformation")
        cfn_template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}
        client.create_stack(
            StackName=stack_name,
            TemplateBody=json.dumps(cfn_template),
            EnableTerminationProtection=True,
        )
        self.addCleanup(client.delete_stack, StackName=stack_name)
        self.addCleanup(
            client.update_termination_protection,
            StackName=stack_name,
            EnableTerminationProtection=False,
        )
        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name).get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-delete-force",
                "resource": "cfn",
                "filters": [{"StackName": stack_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # this should have done nothing.
        stacks = client.describe_stacks(StackName=stack_name).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        self.assertEqual(stacks[0].get("StackStatus"), "CREATE_COMPLETE")

    def test_delete_force(self):
        stack_name = "c7n-test-delete-force"

        factory = self.replay_flight_data("test_cfn_delete_force")
        client = factory().client("cloudformation")
        cfn_template = {"Resources": {"MyTopic": {"Type": "AWS::SNS::Topic"}}}
        client.create_stack(
            StackName=stack_name,
            TemplateBody=json.dumps(cfn_template),
            EnableTerminationProtection=True,
        )
        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name).get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-delete-force",
                "resource": "cfn",
                "filters": [{"StackName": stack_name}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # make sure delete has time to complete
        if self.recording:
            time.sleep(30)

        # deleted stacks must be referenced by StackId
        stacks = client.describe_stacks(StackName=resources[0]["StackId"]).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("StackStatus"), "DELETE_COMPLETE")

    def test_query(self):
        factory = self.replay_flight_data("test_cfn_query")
        p = self.load_policy(
            {"name": "cfn-query", "resource": "cfn"}, session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        for r in resources:
            self.assertTrue("arn" in r['StackId'])
            self.assertTrue("StackName" in r)
            self.assertTrue("Tags" in r)
            self.assertEqual(r["Tags"], [])

    def test_disable_protection(self):
        factory = self.replay_flight_data("test_cfn_disable_protection")
        client = factory().client("cloudformation")
        stacks = client.describe_stacks(StackName="mytopic").get("Stacks")
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), True)
        p = self.load_policy(
            {
                "name": "cfn-disable-protection",
                "resource": "cfn",
                "filters": [{"StackName": "mytopic"}],
                "actions": [{"type": "set-protection", "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("cloudformation")
        stacks = client.describe_stacks(StackName=resources[0]["StackName"]).get(
            "Stacks"
        )
        self.assertEqual(stacks[0].get("EnableTerminationProtection"), False)

    def test_cfn_add_tag_with_params(self):
        session_factory = self.replay_flight_data("test_cfn_add_tag_w_params")
        p = self.load_policy(
            {
                "name": "cfn-add-tag",
                "resource": "cfn",
                "filters": [{"StackName": "mosdef2"}],
                "actions": [{"type": "tag", "tags": {"App": "Ftw"}}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        rtags = {t["Key"]: t["Value"] for t in resources[0]["Tags"]}
        self.assertEqual(rtags, {"Env": "Dev"})
        tags = {
            t["Key"]: t["Value"]
            for t in client.describe_stacks(StackName=resources[0]["StackName"])[
                "Stacks"
            ][0]["Tags"]
        }
        self.assertEqual(tags, {"Env": "Dev", "App": "Ftw"})

    def test_cfn_add_tag(self):
        session_factory = self.replay_flight_data("test_cfn_add_tag")
        p = self.load_policy(
            {
                "name": "cfn-add-tag",
                "resource": "cfn",
                "filters": [{"tag:DesiredTag": "absent"}],
                "actions": [
                    {"type": "tag", "key": "DesiredTag", "value": "DesiredValue"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        tags = client.describe_stacks(StackName=resources[0]["StackName"])["Stacks"][0][
            "Tags"
        ]
        self.assertEqual(
            [tags[0]["Key"], tags[0]["Value"]], ["DesiredTag", "DesiredValue"]
        )

    def test_cfn_remove_tag(self):
        session_factory = self.replay_flight_data("test_cfn_remove_tag")
        p = self.load_policy(
            {
                "name": "cfn-remove-tag",
                "resource": "cfn",
                "filters": [{"tag:DesiredTag": "present"}],
                "actions": [{"type": "remove-tag", "tags": ["DesiredTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("cloudformation")
        tags = client.describe_stacks(StackName=resources[0]["StackName"])["Stacks"][0][
            "Tags"
        ]
        self.assertEqual(len(tags), 0)

    def test_cfn_mark_for_op(self):
        session_factory = self.replay_flight_data("test_cfn_mark_for_op")
        p = self.load_policy(
            {
                "name": "cfn-mark-for-op",
                "resource": "cfn",
                "filters": [{"StackName": "c7n-mark-stack"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("cloudformation")
        tags = client.describe_stacks(StackName=resources[0]["StackName"])["Stacks"][0][
            "Tags"
        ]
        tag_map = {t["Key"]: t["Value"] for t in tags}
        self.assertIn("custodian_cleanup", tag_map)
        self.assertIn("delete", tag_map["custodian_cleanup"])

    def test_cfn_marked_for_op(self):
        session_factory = self.replay_flight_data("test_cfn_marked_for_op")
        p = self.load_policy(
            {
                "name": "cfn-marked-for-delete",
                "resource": "cfn",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "op": "delete",
                        "tag": "custodian_cleanup",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["StackName"], "c7n-marked")

    def test_cfn_template_filter(self):
        session_factory = self.replay_flight_data("test_cfn_template_filter")
        client = session_factory().client("cloudformation")

        stack_name = "c7n-test-template-filter"

        template_body = yaml.dump({
            "Resources": {
                "MyBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": "c7n-access-key-test-bucket"
                    }
                }
            },
            "Metadata": {
                "API_KEY": "API_KEY123456789"
            }
        })

        client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Capabilities=["CAPABILITY_NAMED_IAM"]
        )
        self.addCleanup(client.delete_stack, StackName=stack_name)

        if self.recording:
            time.sleep(30)

        stacks = client.describe_stacks(StackName=stack_name)["Stacks"]
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["StackName"], stack_name)

        policy = self.load_policy(
            {
                "name": "test-cfn-template-filter",
                "resource": "cfn",
                "filters": [
                    {
                        "type": "template",
                        "pattern": "API_KEY[0-9A-Z]",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = policy.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["StackName"], stack_name)

    def test_cfn_topic_filter(self):
        session_factory = self.replay_flight_data("test_cfn_topic_filter")
        p = self.load_policy({
            'name': 'test-cfn-topic-filter',
            'resource': 'aws.cfn',
            'filters': [{
                'type': 'topic',
                'attrs': [{
                    'type': 'value',
                    'key': 'SubscriptionsConfirmed',
                    'value': 0,
                    'value_type': 'integer'
                }]
            }]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:SnsTopics'][0]['SubscriptionsConfirmed'], '0')

    def test_cfn_stack_updatable(self):
        """Test stack state eligibility for tagging operations."""
        from c7n.resources import cfn

        # Updateable states - should return True
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'CREATE_COMPLETE'}))
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'UPDATE_COMPLETE'}))
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'UPDATE_ROLLBACK_COMPLETE'}))
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'IMPORT_COMPLETE'}))
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'IMPORT_ROLLBACK_COMPLETE'}))
        self.assertTrue(cfn._cfn_stack_updatable({'StackStatus': 'ROLLBACK_COMPLETE'}))

        # Non-updateable states - should return False
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'CREATE_IN_PROGRESS'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'UPDATE_IN_PROGRESS'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'DELETE_IN_PROGRESS'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'DELETE_COMPLETE'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'DELETE_FAILED'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'CREATE_FAILED'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'ROLLBACK_IN_PROGRESS'}))
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'UPDATE_ROLLBACK_IN_PROGRESS'}))

        # Edge cases
        self.assertFalse(cfn._cfn_stack_updatable({}))  # Missing StackStatus
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': ''}))  # Empty status
        self.assertFalse(cfn._cfn_stack_updatable({'StackStatus': 'UNKNOWN'}))  # Unknown status

    def test_cfn_tag_skip_non_updateable(self):
        """Test that tagging skips stacks in non-updateable states."""
        stacks = [
            {'StackName': 'stack-ok', 'StackStatus': 'CREATE_COMPLETE', 'Tags': []},
            {'StackName': 'stack-in-progress', 'StackStatus': 'UPDATE_IN_PROGRESS', 'Tags': []},
            {'StackName': 'stack-failed', 'StackStatus': 'DELETE_FAILED', 'Tags': []},
        ]

        action = MagicMock(spec=CloudFormationAddTag)
        action.log = MagicMock()
        tags = [{'Key': 'Test', 'Value': 'Value'}]

        with patch('c7n.resources.cfn._tag_stack') as mock_tag_stack:
            CloudFormationAddTag.process_resource_set(
                action, MagicMock(), stacks, tags)

            # Should only tag the one stack in updateable state
            self.assertEqual(mock_tag_stack.call_count, 1)
            # Verify the stack that was tagged (positional args: client, stack, add=tags)
            call_args = mock_tag_stack.call_args
            tagged_stack = call_args[0][1]  # Second positional arg is the stack
            self.assertEqual(tagged_stack['StackName'], 'stack-ok')

        # Verify warning was logged for skipped stacks
        action.log.warning.assert_called_once()
        warning_args = action.log.warning.call_args[0]
        self.assertIn('2', str(warning_args))  # 2 stacks skipped

    def test_cfn_remove_tag_skip_non_updateable(self):
        """Test that removing tags skips stacks in non-updateable states."""
        tags = [{'Key': 'Test', 'Value': 'Value'}]
        stacks = [
            {'StackName': 'stack-ok', 'StackStatus': 'UPDATE_COMPLETE', 'Tags': tags},
            {'StackName': 'stack-in-progress', 'StackStatus': 'CREATE_IN_PROGRESS',
             'Tags': tags},
        ]

        action = MagicMock(spec=CloudFormationRemoveTag)
        action.log = MagicMock()

        with patch('c7n.resources.cfn._tag_stack') as mock_tag_stack:
            CloudFormationRemoveTag.process_resource_set(
                action, MagicMock(), stacks, ['Test'])

            # Should only process the one stack in updateable state
            self.assertEqual(mock_tag_stack.call_count, 1)

        # Verify warning was logged for skipped stack
        action.log.warning.assert_called_once()
        warning_args = action.log.warning.call_args[0]
        self.assertIn('1', str(warning_args))  # 1 stack skipped
