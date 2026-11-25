from unittest.mock import MagicMock

import boto3
import moto
import pytest
from botocore.exceptions import ClientError
from pytest_terraform import terraform

from .common import BaseTest, event_data
from c7n.cache import InMemoryCache
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

    def test_event_rule_cloudtrail_mode(self):
        policy = self.load_policy({
            'name': 'event-rule-put-rule',
            'resource': 'aws.event-rule',
            'mode': {
                'type': 'cloudtrail',
                'events': [{
                    'source': 'events.amazonaws.com',
                    'event': 'PutRule',
                    'ids': 'responseElements.ruleArn'}]}})
        self.assertEqual(policy.execution_mode, 'cloudtrail')
        self.assertIn('events:DescribeRule', policy.resource_manager.get_permissions())

    def test_event_rule_cloudtrail_push(self):
        # No ListEventBuses or ListRules flight data is recorded, so this
        # fails if resolving the rule enumerates every bus and rule.
        factory = self.replay_flight_data('test_event_rule_cloudtrail_push')
        policy = self.load_policy({
            'name': 'event-rule-put-rule',
            'resource': 'aws.event-rule',
            'mode': {
                'type': 'cloudtrail',
                'events': [{
                    'source': 'events.amazonaws.com',
                    'event': 'PutRule',
                    'ids': 'responseElements.ruleArn'}]},
            'filters': [
                {'type': 'value', 'key': 'Name', 'op': 'regex', 'value': 'custodian-.*$'},
                {'tag:Owner': 'absent'}]},
            session_factory=factory)
        resources = policy.push(
            {'detail': event_data('event-cloud-trail-put-rule.json'), 'debug': True}, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'custodian-orders-created')
        self.assertEqual(resources[0]['EventBusName'], 'orders-bus')
        self.assertEqual(resources[0]['Tags'], [{'Key': 'Team', 'Value': 'orders'}])
        self.assertNotIn('ResponseMetadata', resources[0])

    @moto.mock_aws
    def test_event_rule_get_resources(self):
        # moto only finds a rule on the bus it was created on, so this checks
        # the bus is read from the arn. Missing rules and buses are skipped.
        client = boto3.client('events', region_name='us-east-1')
        client.create_event_bus(Name='orders-bus')
        client.put_rule(Name='nightly', ScheduleExpression='rate(1 day)')
        client.put_rule(
            Name='order-created', EventBusName='orders-bus',
            EventPattern='{"source": ["orders"]}')
        client.put_rule(Name='hourly', ScheduleExpression='rate(1 hour)')
        policy = self.load_policy(
            {'name': 'event-rule-get', 'resource': 'aws.event-rule'},
            config={'region': 'us-east-1'})
        arn = 'arn:aws:events:us-east-1:123456789012:rule/'
        resources = policy.resource_manager.get_resources([
            arn + 'nightly',
            arn + 'orders-bus/order-created',
            'hourly',
            arn + 'gone',
            arn + 'no-such-bus/nightly',
        ])
        self.assertEqual(
            [(r['Name'], r['EventBusName']) for r in resources],
            [('nightly', 'default'), ('order-created', 'orders-bus'), ('hourly', 'default')])

    @moto.mock_aws
    def test_event_rule_get_resources_ignores_warm_cache(self):
        # the cache is keyed by rule Name, event ids are arns
        boto3.client('events', region_name='us-east-1').put_rule(
            Name='nightly', ScheduleExpression='rate(1 day)')
        policy = self.load_policy(
            {'name': 'event-rule-get', 'resource': 'aws.event-rule'},
            config={'region': 'us-east-1'})
        manager = policy.resource_manager
        manager._cache = InMemoryCache({})
        manager.resources()
        resources = manager.get_resources(
            ['arn:aws:events:us-east-1:123456789012:rule/nightly'])
        self.assertEqual([r['Name'] for r in resources], ['nightly'])

    def test_event_rule_get_resources_partner_bus(self):
        # bus names can contain slashes, rule names can't
        bus = 'aws.partner/example.com/1234/mybus'
        factory = MagicMock()
        factory.region = 'us-east-1'
        client = factory().client('events')
        client.describe_rule.return_value = {'Name': 'my-rule', 'EventBusName': bus, 'Arn': 'x'}
        policy = self.load_policy(
            {'name': 'event-rule-get', 'resource': 'aws.event-rule'},
            session_factory=factory)
        policy.resource_manager.source.get_resources(
            ['arn:aws:events:us-east-1:123456789012:rule/%s/my-rule' % bus])
        client.describe_rule.assert_called_once_with(Name='my-rule', EventBusName=bus)

    def test_event_rule_get_resources_error_keeps_other_ids(self):
        # one id that can't be described doesn't drop the rest
        events = boto3.client('events', region_name='us-east-1')
        not_found = events.exceptions.ResourceNotFoundException
        factory = MagicMock()
        factory.region = 'us-east-1'
        client = factory().client('events')
        client.exceptions.ResourceNotFoundException = not_found
        client.describe_rule.side_effect = [
            not_found({'Error': {'Code': 'ResourceNotFoundException'}}, 'DescribeRule'),
            ClientError({'Error': {'Code': 'ValidationException'}}, 'DescribeRule'),
            {'Name': 'nightly', 'EventBusName': 'default', 'ResponseMetadata': {}},
        ]
        policy = self.load_policy(
            {'name': 'event-rule-get', 'resource': 'aws.event-rule'},
            session_factory=factory)
        resources = policy.resource_manager.source.get_resources(['gone', 'bad', 'nightly'])
        self.assertEqual(resources, [{'Name': 'nightly', 'EventBusName': 'default'}])
        self.assertEqual(client.describe_rule.call_count, 3)


def test_event_rule_target_del_managed(test):
    session_factory = test.replay_flight_data("test_event_rule_target_del_managed")
    log_output = test.capture_logging('custodian.actions')
    policy = test.load_policy(
        {
            "name": "test-event-rule-target-del-managed",
            "resource": "event-rule-target",
            "filters": [{"Id": "autoscaling"}],
            "actions": ["delete"],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    # User was warned we can't delete targets on managed rules without forcing.
    assert log_output.getvalue().strip() == (
        'Unable to delete target "autoscaling" for managed rule "AutoScalingManagedRule".'
        ' Set force to true to remove target.'
    )
    # Target still exists.
    client = session_factory().client('events')
    targets = client.list_targets_by_rule(Rule='AutoScalingManagedRule').get('Targets')
    test.assertEqual(len(targets), 1)
    test.assertEqual(targets[0]['Id'], 'autoscaling')


def test_event_rule_target_del_managed_force(test):
    session_factory = test.replay_flight_data("test_event_rule_target_del_managed_force")
    log_output = test.capture_logging('custodian.actions')
    policy = test.load_policy(
        {
            "name": "test-event-rule-target-del-managed-force",
            "resource": "event-rule-target",
            "filters": [{"Id": "autoscaling"}],
            "actions": [{"type": "delete", "force": True}],
        },
        session_factory=session_factory,
    )

    resources = policy.run()
    test.assertEqual(len(resources), 1)
    # No warning message because we forced.
    assert log_output.getvalue().strip() == ''
    # Target got deleted because we forced.
    client = session_factory().client('events')
    targets = client.list_targets_by_rule(Rule='AutoScalingManagedRule').get('Targets')
    test.assertEqual(targets, [])


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


class ConnectionTest(BaseTest):

    def test_event_connection_query(self):
        factory = self.replay_flight_data("test_event_connection_query")
        p = self.load_policy(
            {
                "name": "query-connections",
                "resource": "aws.event-connection",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted(r["AuthorizationType"] for r in resources),
            ["API_KEY", "BASIC"])
        self.assertTrue(resources[0]["ConnectionArn"].startswith(
            "arn:aws:events:us-east-1:644160558196:connection/"))

    def test_event_connection_basic_auth_filter(self):
        factory = self.replay_flight_data("test_event_connection_query")
        p = self.load_policy(
            {
                "name": "eventbridge-connection-basic-auth",
                "resource": "aws.event-connection",
                "filters": [
                    {
                        "type": "value",
                        "key": "AuthorizationType",
                        "op": "not-in",
                        "value": ["OAUTH_CLIENT_CREDENTIALS", "API_KEY"],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["AuthorizationType"], "BASIC")
        self.assertEqual(resources[0]["Name"], "c7n-test-conn-basic")
