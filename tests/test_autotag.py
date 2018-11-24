# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

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
