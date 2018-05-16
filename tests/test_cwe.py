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

import jmespath
from unittest import TestCase

from .common import event_data, BaseTest, TestConfig as Config

from c7n.cwe import CloudWatchEvents


class CloudWatchRuleTarget(BaseTest):

    def test_target_cross_account_remove(self):
        session_factory = self.replay_flight_data("test_cwe_rule_target_cross")
        client = session_factory().client("events")
        policy = self.load_policy(
            {
                "name": "cwe-cross-account",
                "resource": "event-rule-target",
                "filters": [{"type": "cross-account"}],
                "actions": ["delete"],
            },
            config=Config.empty(),
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        targets = client.list_targets_by_rule(Rule=resources[0]["c7n:parent-id"]).get(
            "Targets"
        )
        self.assertEqual(targets, [])


class CloudWatchEventsFacadeTest(TestCase):

    # DISABLED / Record flight data

    def test_get_ids(self):
        self.assertEqual(
            CloudWatchEvents.get_ids(
                {"detail": event_data("event-cloud-trail-run-instances.json")},
                {"type": "cloudtrail", "events": ["RunInstances"]},
            ),
            ["i-784cdacd", u"i-7b4cdace"],
        )

    def test_get_ids_multiple_events(self):
        d = event_data("event-cloud-trail-run-instances.json")
        d["eventName"] = "StartInstances"

        self.assertEqual(
            CloudWatchEvents.get_ids(
                {"detail": d},
                {
                    "type": "cloudtrail",
                    "events": [
                        # wrong event name
                        {
                            "source": "ec2.amazonaws.com",
                            "event": "CreateTags",
                            "ids": "requestParameters.resourcesSet.items[].resourceId",
                        },
                        # wrong event source
                        {
                            "source": "ecs.amazonaws.com",
                            "event": "StartInstances",
                            "ids": "responseElements.instancesSet.items",
                        },
                        # matches no resource ids
                        {
                            "source": "ec2.amazonaws.com",
                            "event": "StartInstances",
                            "ids": "responseElements.instancesSet2.items[].instanceId",
                        },
                        # correct
                        {
                            "source": "ec2.amazonaws.com",
                            "event": "StartInstances",
                            "ids": "responseElements.instancesSet.items[].instanceId",
                        },
                        # we don't fall off the end
                        {
                            "source": "ec2.amazonaws.com",
                            "event": "StartInstances",
                            "ids": "responseElements.instancesSet.items[]",
                        },
                    ],
                },
            ),
            ["i-784cdacd", u"i-7b4cdace"],
        )

    def test_ec2_state(self):
        self.assertEqual(
            CloudWatchEvents.get_ids(
                event_data("event-instance-state.json"), {"type": "ec2-instance-state"}
            ),
            ["i-a2d74f12"],
        )

    def test_asg_state(self):
        self.assertEqual(
            CloudWatchEvents.get_ids(
                event_data("event-asg-instance-failed.json"),
                {
                    "type": "asg-instance-state",
                    "events": ["EC2 Instance Launch Unsuccessful"],
                },
            ),
            ["CustodianTest"],
        )

    def test_custom_event(self):
        d = {"detail": event_data("event-cloud-trail-run-instances.json")}
        d["detail"]["eventName"] = "StartInstances"
        self.assertEqual(
            CloudWatchEvents.get_ids(
                d,
                {
                    "type": "cloudtrail",
                    "events": [
                        {
                            "event": "StartInstances",
                            "ids": "responseElements.instancesSet.items[].instanceId",
                            "source": "ec2.amazonaws.com",
                        }
                    ],
                },
            ),
            ["i-784cdacd", u"i-7b4cdace"],
        )

    def test_non_cloud_trail_event(self):
        for event in ["event-instance-state.json", "event-scheduled.json"]:
            self.assertFalse(CloudWatchEvents.match(event_data(event)))

    def test_cloud_trail_resource(self):
        self.assertEqual(
            CloudWatchEvents.match(event_data("event-cloud-trail-s3.json")),
            {
                "source": "s3.amazonaws.com",
                "ids": jmespath.compile("detail.requestParameters.bucketName"),
            },
        )
