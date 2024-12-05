# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import jmespath
import jmespath.parser
import pytest
from pytest_terraform import terraform
from unittest import TestCase

from .common import event_data, BaseTest

from c7n.cwe import CloudWatchEvents
from c7n.resources import cw


class JmespathEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, jmespath.parser.ParsedResult):
            return obj.parsed
        return json.JSONEncoder.default(self, obj)


@pytest.mark.audited
@terraform('event_bridge_bus')
def test_event_bus_describe(test, event_bridge_bus):
    factory = test.replay_flight_data('test_cwe_bus_xaccount')
    p = test.load_policy({
        'name': 'bus-xaccount',
        'resource': 'aws.event-bus',
        'filters': [
            {'tag:Env': 'Sandbox'},
            'cross-account'
        ],
    }, session_factory=factory)
    resources = p.run()
    assert len(resources) == 1
    resources[0]['Name'] == event_bridge_bus[
        'aws_cloudwatch_event_bus.messenger.name']
    assert 'CrossAccountViolations' in resources[0]


@pytest.mark.audited
@terraform('event_bridge_bus')
def test_event_bus_kms_filter(test, event_bridge_bus):
    factory = test.replay_flight_data('test_cwe_bus_kms_filter')
    p = test.load_policy({
        'name': 'bus-kms',
        'resource': 'aws.event-bus',
        'filters': [
            {'type': 'kms-key', 'key': 'c7n:AliasName', 'value': 'alias/test/cwe'}],
    }, session_factory=factory)
    resources = p.run()
    assert len(resources) == 1
    assert len(resources[0]['c7n:matched-kms-key']) == 1


class CloudWatchEventTest(BaseTest):

    def test_event_rule_tags(self):
        factory = self.replay_flight_data('test_cwe_rule_tags')
        client = factory().client('events')
        policy = self.load_policy(
            {
                'name': 'cwe-rule',
                'resource': 'aws.event-rule',
                'filters': [
                    {'tag:App': 'absent'},
                    {'Name': 'cloud-custodian-mailer'}],
                'actions': [
                    {'type': 'tag', 'tags': {'App': 'Custodian'}}]
            }, session_factory=factory, config={'region': 'us-west-2'})
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = {t['Key']: t['Value'] for t in
                client.list_tags_for_resource(
                    ResourceARN=policy.resource_manager.get_arns(resources)[0]).get(
                        'Tags')}
        self.assertEqual(tags, {'App': 'Custodian'})

    def test_event_rule_enable(self):
        factory = self.replay_flight_data('test_cwe_enable_rule')
        client = factory().client('events')
        policy = self.load_policy(
            {
                'name': 'cwe-enable-rule',
                'resource': 'aws.event-rule',
                'actions': [
                    {
                        'type': 'set-rule-state',
                        'enabled': True
                    }
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        response = client.describe_rule(
            Name=resources[0]['Name'])
        self.assertEqual(response['State'], 'ENABLED')

    def test_event_rule_disable(self):
        factory = self.replay_flight_data('test_cwe_disable_rule')
        client = factory().client('events')
        policy = self.load_policy(
            {
                'name': 'cwe-enable-rule',
                'resource': 'aws.event-rule',
                'actions': [
                    {
                        'type': 'set-rule-state',
                        'enabled': False
                    }
                ]
            },
            session_factory=factory,
        )
        resources = policy.run()
        response = client.describe_rule(
            Name=resources[0]['Name'])
        self.assertEqual(response['State'], 'DISABLED')

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
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        targets = client.list_targets_by_rule(Rule=resources[0]["c7n:parent-id"]).get(
            "Targets"
        )
        self.assertEqual(targets, [])

    def test_event_rule_force_delete(self):
        session_factory = self.replay_flight_data("test_cwe_rule_force_delete")
        client = session_factory().client('events')
        policy = self.load_policy({
            "name": "cwe-filter-on-target",
            "resource": "aws.event-rule",
            "filters": [
                {
                    "type": "event-rule-target",
                    "key": "[].Arn",
                    "value": "arn:aws:lambda:us-east-1:644160558196:function:test",
                    "op": "in",
                    "value_type": "swap"
                }
            ],
            "actions": [
                {
                    "type": "delete",
                    "force": True
                }
            ]
        }, session_factory=session_factory)
        resources = policy.run()
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.describe_rule(Name=resources[0]["Name"])
        self.assertEqual(len(resources), 1)

    def test_event_rule_invalid_targets_any(self):
        session_factory = self.replay_flight_data("test_cwe_rule_invalid_targets")
        lambda_client = session_factory().client('lambda')
        sns_client = session_factory().client('sns')
        policy = self.load_policy({
            "name": "cwe-filter-on-invalid-target",
            "resource": "aws.event-rule",
            "filters": [
                {
                    "type": "invalid-targets"
                }
            ],
        }, session_factory=session_factory)
        resources = policy.run()
        invalid_targets = set([
            "arn:aws:lambda:us-east-1:644160558196:function:test",
            "arn:aws:sns:us-east-1:644160558196:foo"])
        self.assertEqual(set(resources[0]["c7n:InvalidTargets"]), invalid_targets)
        with self.assertRaises(lambda_client.exceptions.ClientError):
            lambda_client.get_function(FunctionName="test")
        with self.assertRaises(sns_client.exceptions.NotFoundException):
            sns_client.get_topic_attributes(TopicArn="arn:aws:sns:us-east-1:644160558196:foo")
        res = sns_client.get_topic_attributes(TopicArn="arn:aws:sns:us-east-1:644160558196:test2")
        self.assertTrue(res)

    def test_event_rule_invalid_targets_all(self):
        session_factory = self.replay_flight_data("test_cwe_rule_invalid_targets")
        policy = self.load_policy({
            "name": "cwe-filter-on-invalid-target",
            "resource": "aws.event-rule",
            "filters": [
                {
                    "type": "invalid-targets",
                    "all": True
                }
            ],
        }, session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_filter_resource_with_unknown_target(self):
        r = {
            'Name': 'test-ebs-snapshot',
            'Arn': 'arn:aws:events:us-east-1:644160558196:rule/test-ebs-snapshot',
            'c7n:ChildArns': ['arn:aws:events:us-east-1:644160558196:target/create-snapshot',
                            'arn:aws:lambda:us-east-1:644160558196:function:custodian-code']
        }
        self.assertFalse(
            cw.ValidEventRuleTargetFilter('event-rule').filter_unsupported_resources(r))


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


class EventBusTest(BaseTest):
    def test_event_bus_delete(self):
        factory = self.replay_flight_data("test_event_bus_delete")
        p = self.load_policy(
            {
                "name": "delete-event-bus",
                "resource": "event-bus",
                "filters": [{"Name": "test-event-bus"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted([r["Name"] for r in resources]),
            ["test-event-bus"],
        )
        client = factory().client("events")
        remainder = client.list_event_buses()["EventBuses"]
        self.assertEqual(len(remainder), 1)
        self.assertNotEqual(remainder[0]["Name"], "test-event-bus")
