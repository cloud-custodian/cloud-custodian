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

import six

from .common import BaseTest, event_data
from c7n.exceptions import PolicyValidationError
from c7n.executor import MainThreadExecutor
from c7n.resources.appelb import AppELB, AppELBTargetGroup


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
        self.assertEqual(
            resource["Tags"],
            [
                {"Key": "App", "Value": "ARTIFACTPLATFORM"},
                {"Key": "OwnerContact", "Value": "me@example.com"},
                {"Key": "TeamName", "Value": "Frogger"},
                {"Key": "Env", "Value": "QA"},
                {"Key": "Name", "Value": "Artifact ELB"},
            ],
        )

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
            for key, value in six.iteritems(attribute):
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

    def test_appelb_waf(self):
        factory = self.replay_flight_data("test_appelb_waf")

        p = self.load_policy(
            {
                "name": "appelb-waf",
                "resource": "app-elb",
                "filters": [
                    {"type": "waf-enabled", "web-acl": "waf-default", "state": False}
                ],
                "actions": [{"type": "set-waf", "web-acl": "waf-default"}],
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
                    {"type": "waf-enabled", "web-acl": "waf-default", "state": True}
                ],
            },
            session_factory=factory,
        )
        post_resources = p.run()
        self.assertEqual(
            resources[0]["LoadBalancerArn"], post_resources[0]["LoadBalancerArn"]
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


class TestAppElbIsNOtLoggingFilter(BaseTest):
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
