# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from c7n.actions import AutoTagUser
from c7n.utils import query_instances
from .common import BaseTest, event_data
from mock import MagicMock


class AutoTagCreator(BaseTest):

    def test_auto_tag_assumed(self):
        # verify auto tag works with assumed roles and can optionally update
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "update": True, "tag": "Owner"}],
            },
            session_factory=session_factory,
        )

        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        self.assertEqual(len(resources), 1)
        tags = {t["Key"]: t["Value"] for t in resources[0]["Tags"]}
        self.assertEqual(tags["Owner"], "Bob")

        session = session_factory()
        instances = query_instances(session, InstanceIds=[resources[0]["InstanceId"]])
        tags = {t["Key"]: t["Value"] for t in instances[0]["Tags"]}
        self.assertEqual(tags["Owner"], "Radiant")

    def test_auto_tag_creator(self):
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "tag": "Owner"}],
            },
            session_factory=session_factory,
        )

        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        self.assertEqual(len(resources), 1)

        # Verify tag added
        session = session_factory()
        instances = query_instances(session, InstanceIds=[resources[0]["InstanceId"]])
        tags = {t["Key"]: t["Value"] for t in instances[0]["Tags"]}
        self.assertEqual(tags["Owner"], "c7nbot")

        # Verify we don't overwrite extant
        client = session.client("ec2")
        client.create_tags(
            Resources=[resources[0]["InstanceId"]],
            Tags=[{"Key": "Owner", "Value": "Bob"}],
        )

        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "tag": "Owner"}],
            },
            session_factory=session_factory,
        )

        resources = policy.push(event, None)
        instances = query_instances(session, InstanceIds=[resources[0]["InstanceId"]])
        tags = {t["Key"]: t["Value"] for t in instances[0]["Tags"]}
        self.assertEqual(tags["Owner"], "Bob")

    def test_error_auto_tag_bad_mode(self):
        # mode type is not cloudtrail
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "auto-tag-error",
                "resource": "ec2",
                "mode": {"type": "not-cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "update": True, "tag": "Owner"}],
            },
            session_factory=None,
            validate=False,
        )

    def test_auto_tag_user_class_method_process(self):
        # check that it works with regular IAMUser creator
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                        "principal_id_tag": "CreatorId",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName", "principal_id_tag": "CreatorId"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result["CreatorName"], "c7nbot")
        self.assertEqual(result["CreatorId"], "AIDAJEZOTH6YPO3DY45QW")

        # check that it doesn't set principalId if not specified regular IAMUser creator
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "tag": "CreatorName"}],
            },
            session_factory=session_factory,
        )
        auto_tag_user.data = {"tag": "CreatorName"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result, {"CreatorName": "c7nbot"})

        # check that it sets principalId with assumeRole
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "Owner",
                        "principal_id_tag": "OwnerId",
                    }
                ],
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        auto_tag_user.data = {"tag": "Owner", "principal_id_tag": "OwnerId"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(
            result, {"Owner": "Radiant", "OwnerId": "AROAIFMJLHZRIKEFRKUUF"}
        )

        # check that it does not sets principalId with assumeRole
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [{"type": "auto-tag-user", "tag": "Owner"}],
            },
            session_factory=session_factory,
        )
        auto_tag_user.data = {"tag": "Owner"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result, {"Owner": "Radiant"})

    def test_auto_tag_creator_with_none_userinfo(self):
        event = {
            "detail": event_data("event-cloud-trail-run-instances.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result, None)

    def test_auto_tag_user_with_arn_value_class_method_process(self):
        # check that it works with IAMUser creator
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                        "value": "arn",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName", "value": "arn"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result["CreatorName"], "arn:aws:iam::644160558196:user/c7nbot")

        # check that it works with assumeRole creator
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "Owner",
                        "value": "arn",
                    }
                ],
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        auto_tag_user.data = {"tag": "Owner", "value": "arn"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(
            result, {"Owner": "arn:aws:sts::03412312600:assumed-role/GR_Dev_Developer/Radiant"}
        )

    def test_auto_tag_user_with_username_value_class_method_process(self):
        # check that it works with IAMUser creator
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                        "value": "userName",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName", "value": "userName"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result["CreatorName"], "c7nbot")

        # check that it works with assumeRole creator
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "Owner",
                        "value": "userName",
                    }
                ],
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        auto_tag_user.data = {"tag": "Owner", "value": "userName"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(
            result, {"Owner": "GR_Dev_Developer"}
        )

    def test_auto_tag_user_with_sourceipaddress_value_class_method_process(self):
        # check that it works with IAMUser creator
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                        "value": "sourceIPAddress",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName", "value": "sourceIPAddress"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result["CreatorName"], "204.63.44.142")

        # check that it works with assumeRole creator
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "Owner",
                        "value": "sourceIPAddress",
                    }
                ],
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        auto_tag_user.data = {"tag": "Owner", "value": "sourceIPAddress"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(
            result, {"Owner": "204.63.44.142"}
        )

    def test_auto_tag_user_with_principal_id_value_class_method_process(self):
        # check that it works with IAMUser creator
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator.json"),
            "debug": True,
        }
        session_factory = self.replay_flight_data("test_ec2_autotag_creator")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "CreatorName",
                        "value": "principalId",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.push(event, None)
        auto_tag_user = AutoTagUser()
        auto_tag_user.data = {"tag": "CreatorName", "value": "principalId"}
        auto_tag_user.manager = MagicMock()
        result = auto_tag_user.process(resources, event)
        self.assertEqual(result["CreatorName"], "AIDAJEZOTH6YPO3DY45QW")

        # check that it works with assumeRole creator
        session_factory = self.replay_flight_data("test_ec2_autotag_assumed")
        policy = self.load_policy(
            {
                "name": "ec2-auto-tag",
                "resource": "ec2",
                "mode": {"type": "cloudtrail", "events": ["RunInstances"]},
                "actions": [
                    {
                        "type": "auto-tag-user",
                        "tag": "creatorId",
                        "value": "principalId",
                    }
                ],
            },
            session_factory=session_factory,
        )
        event = {
            "detail": event_data("event-cloud-trail-run-instance-creator-assumed.json"),
            "debug": True,
        }
        resources = policy.push(event, None)
        auto_tag_user.data = {"tag": "CreatorId", "value": "principalId"}
        result = auto_tag_user.process(resources, event)
        self.assertEqual(
            result, {"CreatorId": "AROAIFMJLHZRIKEFRKUUF:Radiant"}
        )
