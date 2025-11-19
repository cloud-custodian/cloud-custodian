# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .common import BaseTest, event_data
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources.appelb import (
    AppELB, AppELBTargetGroup, AppELBDeleteListenerAction, serialize_attribute_value,
)
from unittest.mock import patch
import logging


def test_serialize():
    assert serialize_attribute_value(True) == 'true'
    assert serialize_attribute_value(False) == 'false'
    assert serialize_attribute_value(60) == '60'
    assert serialize_attribute_value('abc') == 'abc'


class AppELBTest(BaseTest):

    def test_appelb_config_event(self):
        session_factory = self.replay_flight_data('test_appelb_config_event')
        p = self.load_policy({
            'name': 'appelb-checker',
            'resource': 'app-elb',
            'mode': {
                'type': 'config-rule'}},
            session_factory=session_factory)
        event = event_data("app-elb-config-event.json", "config")
        result = p.push(event, {})[0]
        self.assertEqual(
            result['DNSName'],
            'internal-test-288037075.us-east-1.elb.amazonaws.com')
        self.assertEqual(
            result['Tags'],
            [{'Key': 'App', 'Value': 'DevTest'},
             {'Key': 'Env', 'Value': 'Dev'}])
        self.assertEqual(
            result['Attributes'],
            {'access_logs.s3.bucket': '',
             'access_logs.s3.enabled': False,
             'access_logs.s3.prefix': '',
             'deletion_protection.enabled': False,
             'idle_timeout.timeout_seconds': 60,
             'routing.http2.enabled': True})

    def test_appelb_config_source(self):
        event = event_data("app-elb.json", "config")
        p = self.load_policy({"name": "appelbcfg", "resource": "app-elb"})
        source = p.resource_manager.get_source("config")
        resource = source.load_resource(event)
        self.maxDiff = None

        assert resource["Tags"] == [
            {"Key": "App", "Value": "ARTIFACTPLATFORM"},
            {"Key": "Env", "Value": "QA"},
            {"Key": "Name", "Value": "Artifactory ELB"},
            {"Key": "OwnerContact", "Value": "me@example.com"},
            {"Key": "TeamName", "Value": "Frogger"},
        ]

    def test_appelb_simple(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_simple")
        p = self.load_policy(
            {"name": "appelb-simple", "resource": "app-elb"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_validate(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "appelb-simple-filter",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "listener",
                        "key": "LoadBalancerName",
                        "matched": True,
                        "value": "alb-1",
                    }
                ],
            },
        )

        try:
            self.load_policy(
                {
                    "name": "appelb-simple-filter",
                    "resource": "app-elb",
                    "filters": [
                        {
                            "type": "listener",
                            "key": "LoadBalancerName",
                            "value": "alb-1",
                        },
                        {
                            "type": "listener",
                            "key": "LoadBalancerName",
                            "matched": True,
                            "value": "alb-1",
                        },
                    ],
                }
            )
        except PolicyValidationError:
            raise
            self.fail("filter validation should not have failed")

    def test_appelb_simple_filter(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_simple")
        p = self.load_policy(
            {
                "name": "appelb-simple-filter",
                "resource": "app-elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "alb-1"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_default_vpc_filter(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_default_vpc")
        p = self.load_policy(
            {
                "name": "appelb-default-vpc",
                "resource": "app-elb",
                "filters": [{"type": "default-vpc"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_tags_filter(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_simple")
        p = self.load_policy(
            {
                "name": "appelb-tags-filter",
                "resource": "app-elb",
                "filters": [{"tag:KEY1": "VALUE1"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "appelb-tags-filter",
                "resource": "app-elb",
                "filters": [{"tag:KEY1": "VALUE2"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_is_https_filter(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_is_https")
        p = self.load_policy(
            {
                "name": "appelb-is-https-filter",
                "resource": "app-elb",
                "filters": [{"type": "listener", "key": "Protocol", "value": "HTTPS"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_modify_listener(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_modify_listener")
        client = session_factory().client("elbv2")
        p = self.load_policy(
            {
                "name": "appelb-modify-listener-policy",
                "resource": "app-elb",
                "filters": [{"type": "listener", "key": "Port", "value": 8080}],
                "actions": [{"type": "modify-listener", "port": 80}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["LoadBalancerArn"]
        listeners = client.describe_listeners(LoadBalancerArn=arn)["Listeners"]
        self.assertEqual(listeners[0]["Port"], 80)

    def test_appelb_target_group_filter(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_instance_count_non_zero")
        p = self.load_policy(
            {
                "name": "appelb-target-group-filter",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "target-group",
                        "key": "length([?Protocol=='HTTP'])",
                        "value": 1,
                        "op": "eq",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_instance_count_filter_zero(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_instance_count_zero")
        p = self.load_policy(
            {
                "name": "appelb-instance-count-filter-zero",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "target-group",
                        "key": "max([].length(TargetHealthDescriptions))",
                        "value": 0,
                        "op": "eq",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_instance_count_filter_non_zero(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_instance_count_non_zero")
        p = self.load_policy(
            {
                "name": "appelb-instance-count-filter-non-zero",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "target-group",
                        "key": "max([].length(TargetHealthDescriptions))",
                        "value": 0,
                        "op": "gt",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_add_tag(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_add_tag")
        p = self.load_policy(
            {
                "name": "appelb-add-tag",
                "resource": "app-elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "alb-1"}
                ],
                "actions": [{"type": "tag", "key": "KEY42", "value": "VALUE99"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_remove_tag(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_remove_tag")
        p = self.load_policy(
            {
                "name": "appelb-remove-tag",
                "resource": "app-elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "alb-1"}
                ],
                "actions": [{"type": "remove-tag", "tags": ["KEY42"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_mark_for_delete(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_mark_for_delete")
        p = self.load_policy(
            {
                "name": "appelb-mark-for-delete",
                "resource": "app-elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "alb-1"}
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "delete",
                        "tag": "custodian_next",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_delete(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_delete")
        p = self.load_policy(
            {
                "name": "appelb-delete",
                "resource": "app-elb",
                "filters": [
                    {"type": "value", "key": "LoadBalancerName", "value": "alb-2"}
                ],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_delete_force(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_delete_force")
        client = session_factory().client("elbv2")
        p = self.load_policy(
            {
                "name": "appelb-modify-listener-policy",
                "resource": "app-elb",
                "filters": [{"type": "listener", "key": "Port", "value": 80}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["LoadBalancerArn"]
        attributes = client.describe_load_balancer_attributes(LoadBalancerArn=arn)[
            "Attributes"
        ]
        for attribute in attributes:
            for key, value in attribute.items():
                if "deletion_protection.enabled" in key:
                    self.assertTrue(value)
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "appelb-modify-listener-policy",
                "resource": "app-elb",
                "filters": [{"type": "listener", "key": "Port", "value": 80}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_modify_attributes(self):
        session_factory = self.replay_flight_data(
            "test_appelb_modify_attributes")
        client = session_factory().client("elbv2")
        p = self.load_policy(
            {
                "name": "appelb-enable-deletion-protection",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "deletion_protection.enabled",
                        "value": False,
                    },
                ],
                "actions": [
                    {
                        "type": "modify-attributes",
                        "attributes": {
                            "deletion_protection.enabled": "true",
                        },
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["LoadBalancerArn"]
        attrs = client.describe_load_balancer_attributes(
            LoadBalancerArn=arn)["Attributes"]
        attrs = {obj['Key']: obj['Value'] for obj in attrs}
        assert attrs['deletion_protection.enabled'] == 'true'

    def test_appelb_waf_any(self):
        factory = self.replay_flight_data("test_appelb_waf")
        p = self.load_policy({
            "name": "appelb-waf",
            "resource": "app-elb",
            "filters": [
                {"type": "waf-enabled", "state": False}]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['LoadBalancerName'], 'test')

    def test_appelb_waf(self):
        factory = self.replay_flight_data("test_appelb_waf")

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "web-acl": "test", "state": False}
                ],
                "actions": [{"type": "set-waf", "web-acl": "test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "web-acl": "test", "state": True}
                ],
            },
            session_factory=factory,
        )
        post_resources = p.run()
        self.assertEqual(
            resources[0]["LoadBalancerArn"], post_resources[0]["LoadBalancerArn"]
        )

    def test_appelb_waf_value(self):
        factory = self.replay_flight_data("test_appelb_waf_value")

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "key": "Rules", "value": "empty"}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock data contains one rule and will not match
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "key": "length(Rules[?Type == 'REGULAR'])", "value": 1}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock data contains one "REGULAR" rule
        self.assertEqual(len(resources), 1)

    def test_appelb_wafv2_any(self):
        factory = self.replay_flight_data("test_appelb_wafv2")
        p = self.load_policy({
            "name": "appelb-wafv2",
            "resource": "app-elb",
            "filters": [
                {"type": "wafv2-enabled", "state": False}]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['LoadBalancerName'], 'test')

    def test_appelb_wafv2(self):
        factory = self.replay_flight_data("test_appelb_wafv2")

        p = self.load_policy(
            {
                "name": "appelb-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "web-acl": "testv2", "state": False}
                ],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        p = self.load_policy(
            {
                "name": "appelb-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "web-acl": "testv2", "state": True}
                ],
            },
            session_factory=factory,
        )
        post_resources = p.run()
        self.assertEqual(
            resources[0]["LoadBalancerArn"], post_resources[0]["LoadBalancerArn"]
        )

    def test_appelb_wafv2_to_waf(self):
        factory = self.replay_flight_data("test_appelb_wafv2")

        p = self.load_policy(
            {
                "name": "appelb-wafv2-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "web-acl": "testv2", "state": False}
                ],
                "actions": [{"type": "set-waf", "web-acl": "test"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_wafv2_value(self):
        factory = self.replay_flight_data("test_appelb_wafv2_value")

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [{"type": "wafv2-enabled", "key": "Rules", "value": "empty"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock data contains one rule and will not match
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [{
                    "type": "wafv2-enabled",
                    "key": "length(Rules[?contains(keys(Statement), 'RateBasedStatement')])",
                    "op": "gte",
                    "value": 1
                }]
            },
            session_factory=factory,
        )
        resources = p.run()
        # mock WAF rule has single RateBasedStatement
        self.assertEqual(len(resources), 1)

    def test_appelb_waf_to_wafv2(self):
        factory = self.replay_flight_data("test_appelb_waf")

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "web-acl": "test", "state": False}
                ],
                "actions": [{"type": "set-wafv2", "web-acl": "testv2"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_filter_wafv2_regex(self):
        factory = self.replay_flight_data("test_appelb_wafv2_regex")

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "state": False}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled",
                     "web-acl": "FMManagedWebACLV2-FMS-.*",
                     "state": True}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "web-acl": "testv3",
                     "state": False}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_action_wafv2_not_found(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"state": False}
                ],
                "actions": [
                    {"type": "set-wafv2", "web-acl": "FMManagedWebACLV2-FMS-T.*"}
                ],
            },
        )

    def test_appelb_action_wafv2_regex_multiple_webacl_match(self):
        factory = self.replay_flight_data(
            "test_appelb_wafv2_regex_multiple_webacl_match")

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled", "state": True}
                ],
                "actions": [
                    {"type": "set-wafv2", "web-acl": "FMManagedWebACLV2-FMS-T.*"}
                ],
            },
            session_factory=factory,
        )
        with self.assertRaises(ValueError) as ctx:
            p.run()
            self.assertTrue('matching to none or multiple webacls' in str(
                ctx.exception))

    def test_appelb_action_wafv2_regex_disassociate_webacl(self):
        factory = self.replay_flight_data(
            "test_appelb_wafv2_regex")

        p = self.load_policy(
            {
                "name": "appelb-waf-wafv2",
                "resource": "app-elb",
                "filters": [
                    {"type": "wafv2-enabled",
                     "web-acl": "FMManagedWebACLV2-FMS-T.*", "state": True}
                ],
                "actions": [
                    {"type": "set-wafv2", "state": False}
                ],
            },
            session_factory=factory,
        )
        response = p.run()
        self.assertEqual(response[0]['LoadBalancerName'], 'test')

    def test_set_wafv2_active_response(self):
        factory = self.replay_flight_data("test_appelb_wafv2")
        policy = self.load_policy(
            {
                "name": "waf-appelb-active-response",
                "resource": "app-elb",
                "mode": {"type": "cloudtrail", "events": [{
                    "source": "elasticloadbalancing.amazonaws.com",
                    "ids": "requestParameters.resourceArns[0]",
                    "event": "AddTags"
                }]},
                "filters": [{"type": "wafv2-enabled", "state": False}, {"tag:WAF": "Internal"}],
                "actions": [{"type": "set-wafv2", "state": True, "web-acl": "testv2"}],
            },
            session_factory=factory,
        )

        resources = policy.push(event_data("event-cloud-trail-appelb-add-tags.json"))
        self.assertEqual(len(resources), 1)

    def test_appelb_net_metrics(self):
        factory = self.replay_flight_data('test_netelb_metrics')
        p = self.load_policy({
            'name': 'netelb-metrics',
            'resource': 'app-elb',
            'filters': [
                {'Type': 'network'},
                {'type': 'metrics',
                 'name': 'TCP_ELB_Reset_Count',
                 'namespace': 'AWS/NetworkELB',
                 'statistics': 'Sum',
                 'value': 10,
                 'op': 'greater-than',
                 'days': 0.25}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['LoadBalancerName'], 'nicnoc')
        self.assertTrue(
            'AWS/NetworkELB.TCP_ELB_Reset_Count.Sum.0.25' in resources[
                0]['c7n.metrics'])

    def test_appelb_delete_listener(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_delete_listener")
        client = session_factory().client("elbv2")
        # Create a policy that deletes listeners on a specific port
        p = self.load_policy(
            {
                "name": "appelb-delete-listener",
                "resource": "app-elb",
                "filters": [
                    {"type": "listener", "key": "[Protocol, Port]", "value": ["HTTP", 5432]}
                ],
                "actions": [{"type": "delete-listener"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        arn = resources[0]["LoadBalancerArn"]
        listeners = client.describe_listeners(LoadBalancerArn=arn)["Listeners"]
        # Assert that no listeners remain on the specified port
        for l in listeners:
            assert not (l["Protocol"] == "HTTP" and l["Port"] == 5432)

    def test_appelb_delete_listener_not_found_exception(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_delete_listener_not_found_exception")
        client = session_factory().client("elbv2")

        class ListenerNotFound(Exception):
            pass
        client.exceptions.ListenerNotFoundException = ListenerNotFound

        called = []

        def fake_delete_listener(**kwargs):
            called.append(True)
            raise ListenerNotFound("Listener not found")
        client.delete_listener = fake_delete_listener
        dummy_listener_arn = (
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/alb-testing-2/95e544fad78114e5/1234567890abcdef"
    )
        load_balancer_arn = (
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/alb-testing-2/95e544fad78114e5")
        alb = {
            "LoadBalancerArn": load_balancer_arn,
            "c7n:MatchedListeners": [
                {
                    "ListenerArn": dummy_listener_arn
                }
            ],
        }

        logger = logging.getLogger("test")

        # Patch local_session only within this block
        with patch("c7n.resources.appelb.local_session",
                   return_value=type("Session", (), {"client": lambda self, service: client})()
                   ):
            action = AppELBDeleteListenerAction(
                data={"type": "delete-listener"},
                manager=type(
                    "mgr", (), {
                        "session_factory": session_factory, "log": logger, "data": {}
                        }
                    )()
            )
            action.process([alb])
        self.assertTrue(called, "delete_listener is called")

    def test_appelb_delete_listener_validation_failure(self):
        # Loading a policy without a listener filter should fail validation
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "delete-listener-no-filter",
                    "resource": "app-elb",
                    "actions": [{"type": "delete-listener"}],
                }
            )


class AppELBHealthcheckProtocolMismatchTest(BaseTest):

    def test_appelb_healthcheck_protocol_mismatch_filter_good(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_appelb_healthcheck_protocol_mismatch_good"
        )
        p = self.load_policy(
            {
                "name": "appelb-healthcheck-protocol-mismatch-good",
                "resource": "app-elb",
                "filters": ["healthcheck-protocol-mismatch"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_healthcheck_protocol_mismatch_filter_bad(self):
        self.patch(AppELB, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_appelb_healthcheck_protocol_mismatch_bad"
        )
        p = self.load_policy(
            {
                "name": "appelb-healthcheck-protocol-mismatch-bad",
                "resource": "app-elb",
                "filters": ["healthcheck-protocol-mismatch"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)


class AppELBTargetGroupTest(BaseTest):

    def test_appelb_target_group_simple(self):
        self.patch(AppELBTargetGroup, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_target_group_simple")
        p = self.load_policy(
            {"name": "appelb-target-group-simple", "resource": "app-elb-target-group"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_target_group_simple_filter(self):
        self.patch(AppELBTargetGroup, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_target_group_simple")
        p = self.load_policy(
            {
                "name": "appelb-target-group-simple-filter",
                "resource": "app-elb-target-group",
                "filters": [{"type": "value", "key": "Port", "value": 443}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_target_group_default_vpc(self):
        self.patch(AppELBTargetGroup, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data(
            "test_appelb_target_group_default_vpc"
        )
        p = self.load_policy(
            {
                "name": "appelb-target-group-default-vpc",
                "resource": "app-elb-target-group",
                "filters": [{"type": "default-vpc"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_target_group_delete(self):
        self.patch(AppELBTargetGroup, "executor_factory", MainThreadExecutor)
        session_factory = self.replay_flight_data("test_appelb_target_group_delete")

        policy = self.load_policy(
            {
                "name": "app-elb-delete-target-group",
                "resource": "app-elb-target-group",
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(len(resources), 0, "Test should delete app elb target group")

    def test_target_group_modify_attributes(self):
        session_factory = self.replay_flight_data(
            "test_target_group_attributes_filter_action")
        client = session_factory().client("elbv2")
        p = self.load_policy(
            {
                "name": "target-group-enable-preserve-client-ip",
                "resource": "app-elb-target-group",
                "filters": [
                    {
                        "type": "attributes",
                        "key": "preserve_client_ip.enabled",
                        "value": False,
                    },
                ],
                "actions": [
                    {
                        "type": "modify-attributes",
                        "attributes": {
                            "preserve_client_ip.enabled": "true",
                        },
                    },
                ],
            },
            config={'region': 'us-west-2'},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]["TargetGroupArn"]
        attrs = client.describe_target_group_attributes(
            TargetGroupArn=arn)["Attributes"]
        attrs = {obj['Key']: obj['Value'] for obj in attrs}
        assert attrs['preserve_client_ip.enabled'] == 'true'


class TestAppElbLogging(BaseTest):

    def test_enable_s3_logging(self):
        session_factory = self.replay_flight_data("test_appelb_enable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-enable-s3-logging",
                "resource": "app-elb",
                "filters": [{"LoadBalancerName": "alb1"}],
                "actions": [
                    {
                        "type": "set-s3-logging",
                        "state": "enabled",
                        "bucket": "elbv2logtest",
                        "prefix": "elblogs/{LoadBalancerName}",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("elbv2")
        attrs = {
            t["Key"]: t["Value"]
            for t in client.describe_load_balancer_attributes(
                LoadBalancerArn=resources[0]["LoadBalancerArn"]
            ).get(
                "Attributes"
            )
        }
        self.assertEqual(
            attrs,
            {
                "access_logs.s3.enabled": "true",
                "access_logs.s3.bucket": "elbv2logtest",
                "access_logs.s3.prefix": "gah5/alb1",
            },
        )

    def test_disable_s3_logging(self):
        session_factory = self.replay_flight_data("test_appelb_disable_s3_logging")
        policy = self.load_policy(
            {
                "name": "test-disable-s3-logging",
                "resource": "app-elb",
                "filters": [{"LoadBalancerName": "alb1"}],
                "actions": [{"type": "set-s3-logging", "state": "disabled"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("elbv2")
        attrs = {
            t["Key"]: t["Value"]
            for t in client.describe_load_balancer_attributes(
                LoadBalancerArn=resources[0]["LoadBalancerArn"]
            ).get(
                "Attributes"
            )
        }
        self.assertEqual(
            attrs,
            {
                "access_logs.s3.enabled": "false",
                "access_logs.s3.bucket": "elbv2logtest",
                "access_logs.s3.prefix": "gah5",
            },
        )


class TestAppElbIsLoggingFilter(BaseTest):
    """ replicate
        - name: appelb-is-logging-to-bucket-test
          resource: app-elb
          filters:
            - type: is-logging
            bucket: elbv2logtest
    """

    def test_is_logging_to_bucket(self):
        session_factory = self.replay_flight_data("test_appelb_is_logging_filter")
        policy = self.load_policy(
            {
                "name": "appelb-is-logging-to-bucket-test",
                "resource": "app-elb",
                "filters": [{"type": "is-logging", "bucket": "elbv2logtest"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(
            len(resources), 0, "Test should find appelbs logging " "to elbv2logtest"
        )


class TestHealthEventsFilter(BaseTest):

    def test_rds_health_events_filter(self):
        session_factory = self.replay_flight_data("test_appelb_health_events_filter")
        policy = self.load_policy(
            {
                "name": "appelb-health-events-filter",
                "resource": "app-elb",
                "filters": [{"type": "health-event", "statuses": ["open", "upcoming", "closed"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestAppElbIsNotLoggingFilter(BaseTest):
    """ replicate
        - name: appelb-is-not-logging-to-bucket-test
          resource: app-elb
          filters:
            - type: is-not-logging
            bucket: elbv2logtest
    """

    def test_is_logging_to_bucket(self):
        session_factory = self.replay_flight_data("test_appelb_is_logging_filter")
        policy = self.load_policy(
            {
                "name": "appelb-is-logging-to-bucket-test",
                "resource": "app-elb",
                "filters": [{"type": "is-not-logging", "bucket": "otherbucket"}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertGreater(
            len(resources), 0, "Test should find appelbs not" "logging to otherbucket"
        )


class TestAppElbAttributesFilter(BaseTest):

    def test_nlb_is_cross_zone_load_balancing(self):
        session_factory = self.replay_flight_data("test_netelb_attributes_filter")
        policy = self.load_policy(
            {
                "name": "netelb-is-cross-zone-balancing",
                "resource": "app-elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "load_balancing.cross_zone_enabled",
                            "value": True,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 0, "Test should find no net lb with cross zone load balancing enabled"
        )

    def test_nlb_is_not_cross_zone_load_balancing(self):
        session_factory = self.replay_flight_data("test_netelb_attributes_filter")
        policy = self.load_policy(
            {
                "name": "netelb-is-not-cross-zone-balancing",
                "resource": "app-elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "load_balancing.cross_zone_enabled",
                            "value": False,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find 1 net lb with cross zone load balancing disabled"
        )

        self.assertEqual(
            resources[0]['Attributes']['load_balancing.cross_zone_enabled'], False
        )

    def test_alb_http2_is__enabled(self):
        session_factory = self.replay_flight_data("test_appelb_attributes_filter")
        policy = self.load_policy(
            {
                "name": "appelb-http2-is-enabled",
                "resource": "app-elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "routing.http2.enabled",
                            "value": True,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find 1 app lb with http2 enabled"
        )

        self.assertEqual(
            resources[0]['Attributes']['routing.http2.enabled'], True
        )

    def test_alb_http2_is_not_enabled(self):
        session_factory = self.replay_flight_data("test_appelb_attributes_filter")
        policy = self.load_policy(
            {
                "name": "appelb-http2-is-not-enabled",
                "resource": "app-elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "routing.http2.enabled",
                            "value": False,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 0, "Test should find 0 app lb with http2 enabled"
        )

    def test_alb_idle_timeout_below_60(self):
        session_factory = self.replay_flight_data("test_appelb_attributes_filter")
        policy = self.load_policy(
            {
                "name": "appelb-idle-timeout-is-below-60",
                "resource": "app-elb",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "idle_timeout.timeout_seconds",
                            "value": 60,
                            "op": "lt"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find 1 app lb with idle timeout < 60s"
        )

        self.assertLess(
            resources[0]['Attributes']['idle_timeout.timeout_seconds'], 60
        )


class TestModifyVpcSecurityGroupsAction(BaseTest):

    def test_appelb_remove_matched_security_groups(self):

        # Test conditions:
        #   - list contains only one ALB, 'test-abc'
        #   - has two SGs attached before, 1 SG after
        #   - test checks name of ALB is correct and
        #   - that SGs change and are expected values

        session_factory = self.replay_flight_data(
            "test_appelb_remove_matched_security_groups"
        )

        p = self.load_policy(
            {
                "name": "appelb-remove-matched-security-groups",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-abc",
                        "op": "eq",
                    },
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": ".*controllers",
                        "op": "regex",
                    },
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": "sg-01a19f602ecaf25f4",
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        client = session_factory().client('elbv2')
        response = client.describe_load_balancers()
        clean_resources = response['LoadBalancers']

        self.assertEqual(len(resources), 1)
        self.assertIn("test", resources[0]["LoadBalancerName"])
        self.assertEqual(len(resources[0]["SecurityGroups"]), 2)
        self.assertIn("sg-c573e6b3", resources[0]["SecurityGroups"])
        # check result is expected
        self.assertEqual(len(clean_resources[0]["SecurityGroups"]), 1)
        self.assertNotIn("sg-c573e6b3", clean_resources[0]["SecurityGroups"])

    def test_appelb_add_security_group(self):

        # Test conditions:
        #   - list contains only one ALB, 'test-abc'
        #   - has one SG attached before, 2 SGs after
        #   - test checks name of ALB is correct and
        #   - that SGs change and are expected values

        session_factory = self.replay_flight_data("test_appelb_add_security_group")

        p = self.load_policy(
            {
                "name": "add-sg-to-appelb",
                "resource": "app-elb",
                "filters": [
                    {
                        "type": "value",
                        "key": "LoadBalancerName",
                        "value": "test-abc",
                        "op": "eq",
                    },
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-c573e6b3"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        client = session_factory().client('elbv2')
        response = client.describe_load_balancers()
        clean_resources = response['LoadBalancers']

        self.assertEqual(len(resources), 1)
        self.assertEqual("test-abc", resources[0]["LoadBalancerName"])
        self.assertEqual(len(resources[0]["SecurityGroups"]), 1)
        self.assertNotIn("sg-c573e6b3", resources[0]["SecurityGroups"])
        # check SG was added
        self.assertEqual(len(clean_resources[0]["SecurityGroups"]), 2)
        self.assertIn("sg-c573e6b3", clean_resources[0]["SecurityGroups"])


class TestTargetGroupAttributesFilter(BaseTest):
    def test_is_not_preserve_client_ip_target_group(self):
        session_factory = self.replay_flight_data("test_target_group_attributes_filter_action")
        policy = self.load_policy(
            {
                "name": "target-group-is-not-preserve-client-ip",
                "resource": "app-elb-target-group",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "preserve_client_ip.enabled",
                            "value": False,
                            "op": "eq",
                        }
                ],
            },
            config={'region': 'us-west-2'},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_is_preserve_client_ip_target_group(self):
        session_factory = self.replay_flight_data("test_target_group_attributes_filter_action")
        policy = self.load_policy(
            {
                "name": "target-group-is-preserve-client-ip",
                "resource": "app-elb-target-group",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "preserve_client_ip.enabled",
                            "value": True,
                            "op": "eq",
                        }
                ],
            },
            config={'region': 'us-west-2'},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_target_group_stickiness_type_check(self):
        session_factory = self.replay_flight_data("test_target_group_attributes_filter_action")
        policy = self.load_policy(
            {
                "name": "target-group-stickiness-is-source_ip",
                "resource": "app-elb-target-group",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "stickiness.type",
                            "value": "source_ip",
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1,
            "Test should find 1 target group with stickiness with source_ip enabled"
        )

        self.assertEqual(
            resources[0]['c7n:TargetGroupAttributes']['stickiness.type'], "source_ip"
        )

    def test_tg_deregistration_delay_timeout_equal_300(self):
        session_factory = self.replay_flight_data("test_target_group_attributes_filter_action")
        policy = self.load_policy(
            {
                "name": "target-group-idle-timeout-is-equal-300",
                "resource": "app-elb-target-group",
                "filters": [
                        {
                            "type": "attributes",
                            "key": "deregistration_delay.timeout_seconds",
                            "value": 300,
                            "op": "eq"
                        }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()

        self.assertEqual(
            len(resources), 1, "Test should find 1 target group with idle timeout == 300s"
        )

        self.assertEqual(
            resources[0]['c7n:TargetGroupAttributes']['deregistration_delay.timeout_seconds'], 300
        )
