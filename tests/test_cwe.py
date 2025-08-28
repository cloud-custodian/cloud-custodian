# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import jmespath
import jmespath.parser
from unittest import TestCase

from .common import event_data

from c7n.cwe import CloudWatchEvents


class JmespathEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, jmespath.parser.ParsedResult):
            return obj.parsed
        return json.JSONEncoder.default(self, obj)


class CloudWatchEventsFacadeTest(TestCase):

    def test_get_ids(self):
        self.assertEqual(
            CloudWatchEvents.get_ids(
                {"detail": event_data("event-cloud-trail-run-instances.json")},
                {"type": "cloudtrail", "events": ["RunInstances"]},
            ),
            ["i-784cdacd", "i-7b4cdace"],
        )

    def test_get_ids_sans_with_details_expr(self):
        self.assertEqual(
            CloudWatchEvents.get_ids(
                {'detail': event_data('event-cloud-trail-run-instances.json')},
                {'type': 'cloudtrail', 'events': [
                    {'ids': 'detail.responseElements.instancesSet.items[].instanceId',
                     'source': 'ec2.amazonaws.com',
                     'event': 'RunInstances'}]}),
            ["i-784cdacd", "i-7b4cdace"],
        )

    def test_get_ids_sans_without_details_expr(self):
        self.assertEqual(
            sorted(CloudWatchEvents.get_ids(
                {'detail': event_data('event-cloud-trail-run-instances.json')},
                {'type': 'cloudtrail', 'events': [
                    {'ids': 'responseElements.instancesSet.items[].instanceId',
                     'source': 'ec2.amazonaws.com',
                     'event': 'RunInstances'}
                ]})),
            ["i-784cdacd", "i-7b4cdace"],
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
        matched_event = CloudWatchEvents.match(event_data("event-cloud-trail-s3.json"))
        expected_event = {
            "source": "s3.amazonaws.com",
            "ids": jmespath.compile("detail.requestParameters.bucketName"),
        }

        self.assertEqual(
            json.dumps(matched_event, sort_keys=True, cls=JmespathEncoder),
            json.dumps(expected_event, sort_keys=True, cls=JmespathEncoder),
        )
