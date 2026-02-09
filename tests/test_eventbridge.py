import pytest
from pytest_terraform import terraform

from .common import BaseTest
from c7n.resources import eventbridge


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


class EventBusTest(BaseTest):
    def test_event_bus_delete(self):
        factory = self.replay_flight_data("test_event_bus_delete", region="us-west-1")
        p = self.load_policy(
            {
                "name": "delete-event-bus",
                "resource": "event-bus",
                "filters": [{"Name": "test-event-bus"}],
                "actions": ["delete"],
            },
            session_factory=factory, config={'region': 'us-west-1'}
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


class EventRuleTest(BaseTest):

    def test_event_rule_target_event_rule(self):
        session_factory = self.replay_flight_data("test_event_rule_target_event_rule",
                                                  region='us-west-1')
        policy = self.load_policy(
            {
                "name": "cwe-event-rule-target",
                "resource": "event-rule-target",
                "filters": [{
                        "type": "value",
                        "key": "Arn",
                        "op": "eq",
                        "value": "arn:aws:sns:us-west-1:644160558196:topic-2",
                    }]
            },
            config={'region': 'us-west-1'},
            session_factory=session_factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_event_rule_tags(self):
        factory = self.replay_flight_data('test_cwe_rule_tags', region='us-west-1')
        client = factory().client('events')
        policy = self.load_policy(
            {
                'name': 'cwe-rule',
                'resource': 'aws.event-rule',
                'filters': [
                    {'tag:App': 'absent'},],
                'actions': [
                    {'type': 'tag', 'tags': {'App': 'Custodian'}}]
            }, session_factory=factory, config={'region': 'us-west-1'})
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        tags = {t['Key']: t['Value'] for t in
                client.list_tags_for_resource(
                    ResourceARN=policy.resource_manager.get_arns(resources)[0]).get(
                        'Tags')}
        self.assertEqual(tags, {'App': 'Custodian'})

    def test_event_rule_enable(self):
        factory = self.replay_flight_data('test_cwe_enable_rule', region='us-west-1')
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
            session_factory=factory, config={'region': 'us-west-1'}
        )
        resources = policy.run()
        response = client.describe_rule(
            Name=resources[0]['Name'])
        self.assertEqual(response['State'], 'ENABLED')

    def test_event_rule_disable(self):
        factory = self.replay_flight_data('test_cwe_disable_rule', region='us-west-1')
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
            session_factory=factory, config={'region': 'us-west-1'}
        )
        resources = policy.run()
        response = client.describe_rule(
            Name=resources[0]['Name'])
        self.assertEqual(response['State'], 'DISABLED')

    def test_target_cross_account_remove(self):
        session_factory = self.replay_flight_data("test_cwe_rule_target_cross", region="us-west-1")
        client = session_factory().client("events")
        policy = self.load_policy(
            {
                "name": "cwe-cross-account",
                "resource": "event-rule-target",
                "filters": [{"type": "cross-account"}],
                "actions": ["delete"],
            },
            session_factory=session_factory, config={'region': 'us-west-1'}
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        rule_id = resources[0]["c7n:parent-id"]
        event_bus = resources[0]["Rule"]["EventBusName"]
        targets = client.list_targets_by_rule(Rule=rule_id, EventBusName=event_bus).get(
            "Targets"
        )
        self.assertEqual(targets, [])

    def test_event_rule_force_delete(self):
        session_factory = self.replay_flight_data("test_cwe_rule_force_delete", region="us-west-1")
        client = session_factory().client('events')
        policy = self.load_policy({
            "name": "cwe-filter-on-target",
            "resource": "aws.event-rule",
            "filters": [
                {
                    "type": "event-rule-target",
                    "key": "[].Arn",
                    "value": "arn:aws:lambda:us-west-1:644160558196:function:test",
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
        }, session_factory=session_factory, config={'region': 'us-west-1'})
        resources = policy.run()
        with self.assertRaises(client.exceptions.ResourceNotFoundException):
            client.describe_rule(Name=resources[0]["Name"])
        self.assertEqual(len(resources), 1)

    def test_event_rule_invalid_targets_any(self):
        session_factory = self.replay_flight_data(
            "test_cwe_rule_invalid_targets", region="us-west-1")
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
        }, session_factory=session_factory, config={'region': 'us-west-1'})
        resources = policy.run()
        invalid_targets = set([
            "arn:aws:lambda:us-west-1:644160558196:function:test",
            "arn:aws:sns:us-west-1:644160558196:foo"])
        self.assertEqual(set(resources[0]["c7n:InvalidTargets"]), invalid_targets)
        with self.assertRaises(lambda_client.exceptions.ClientError):
            lambda_client.get_function(FunctionName="test")
        with self.assertRaises(sns_client.exceptions.NotFoundException):
            sns_client.get_topic_attributes(TopicArn="arn:aws:sns:us-west-1:644160558196:foo")

    def test_event_rule_invalid_targets_all(self):
        session_factory = self.replay_flight_data(
            "test_cwe_rule_invalid_targets_all", region="us-west-1")
        policy = self.load_policy({
            "name": "cwe-filter-on-invalid-target",
            "resource": "aws.event-rule",
            "filters": [
                {
                    "type": "invalid-targets",
                    "all": True
                }
            ],
        }, session_factory=session_factory, config={'region': 'us-west-1'})
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
            eventbridge.ValidEventRuleTargetFilter('event-rule').filter_unsupported_resources(r))


class PipesTest(BaseTest):

    def test_event_bridge_pipes_tag(self):
        factory = self.replay_flight_data("test_event_bridge_pipes_tag")
        p = self.load_policy(
            {
                "name": "tag-event-bridge-pipes",
                "resource": "aws.eventbridge-pipes",
                "filters": [{"Name": "c7n-test"}],
                "actions": [{"type": "tag", "tags": {"c7n": "test"}}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "untag-event-bridge-pipes",
                "resource": "aws.eventbridge-pipes",
                "filters": [{"tag:c7n": "test"}],
                "actions": [{"type": "remove-tag", "tags": ["c7n"]}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("pipes")
        response = client.describe_pipe(Name=resources[0]['Name'])
        self.assertEqual(response['Tags'], {})

    def test_event_bridge_pipes_stop(self):
        factory = self.replay_flight_data("test_event_bridge_pipes_stop")
        p = self.load_policy(
            {
                "name": "stop-event-bridge-pipes",
                "resource": "aws.eventbridge-pipes",
                "filters": [{"Name": "c7n-test"}],
                "actions": ["stop"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("pipes")
        response = client.describe_pipe(Name=resources[0]['Name'])
        self.assertEqual(response['CurrentState'], 'STOPPING')

    def test_event_bridge_pipes_delete(self):
        factory = self.replay_flight_data("test_event_bridge_pipes_delete")
        p = self.load_policy(
            {
                "name": "delete-event-bridge-pipes",
                "resource": "aws.eventbridge-pipes",
                "filters": [{"Name": "c7n-test"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("pipes")
        pipes = client.list_pipes()["Pipes"]
        self.assertEqual(pipes[0]["CurrentState"], "DELETING")


class ApiDestinationTest(BaseTest):

    def test_api_destination_query(self):
        factory = self.replay_flight_data("test_api_destination_query")
        p = self.load_policy(
            {
                "name": "query-api-destinations",
                "resource": "aws.event-api-destination",
                "filters": [
                    {
                        "type": "value",
                        "key": "ApiDestinationState",
                        "value": "ACTIVE"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], "test-delete-me")
        self.assertEqual(resources[0]["ApiDestinationState"], "ACTIVE")
