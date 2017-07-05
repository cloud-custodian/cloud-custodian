# Copyright 2016 Capital One Services, LLC
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

from .common import BaseTest
from c7n.executor import MainThreadExecutor
from c7n.resources.appelb import AppELB, AppELBTargetGroup


class AppELBTest(BaseTest):

    def test_appelb_simple(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_simple')
        p = self.load_policy({
            'name': 'appelb-simple',
            'resource': 'app-elb'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_simple_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_simple')
        p = self.load_policy({
            'name': 'appelb-simple-filter',
            'resource': 'app-elb',
            'filters': [
                {'type': 'value',
                 'key': 'LoadBalancerName',
                 'value': 'alb-1'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_default_vpc_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_default_vpc')
        p = self.load_policy({
            'name': 'appelb-default-vpc',
            'resource': 'app-elb',
            'filters': [{'type': 'default-vpc'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_tags_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_simple')
        p = self.load_policy({
            'name': 'appelb-tags-filter',
            'resource': 'app-elb',
            'filters': [{"tag:KEY1": "VALUE1"}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'appelb-tags-filter',
            'resource': 'app-elb',
            'filters': [{"tag:KEY1": "VALUE2"}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_is_https_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_is_https')
        p = self.load_policy({
            'name': 'appelb-is-https-filter',
            'resource': 'app-elb',
            'filters': [
                {'type': 'listener',
                 'key': "Protocol",
                 'value': "HTTPS"}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_modify_listener(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_modify_listener')
        client = session_factory().client('elbv2')
        p = self.load_policy({
            'name': 'appelb-modify-listener-policy',
            'resource': 'app-elb',
            'filters': [{
                'type': 'listener',
                'key': 'Port',
                'value': 8080
            }],
            'actions': [{
                'type': 'modify-listener',
                'port': 80
            }]
            },
            session_factory=session_factory
            )
        resources = p.run()
        arn = resources[0]['LoadBalancerArn']
        listeners = client.describe_listeners(LoadBalancerArn=arn)['Listeners']
        self.assertEqual(listeners[0]['Port'],80)


    def test_appelb_target_group_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_instance_count_non_zero')
        p = self.load_policy({
            'name': 'appelb-target-group-filter',
            'resource': 'app-elb',
            'filters': [
                {'type': 'target-group',
                 'key': "length([?Protocol=='HTTP'])", 'value': 1,
                 'op': 'eq'}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_instance_count_filter_zero(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_instance_count_zero')
        p = self.load_policy({
            'name': 'appelb-instance-count-filter-zero',
            'resource': 'app-elb',
            'filters': [
                {'type': 'target-group',
                 'key': "max([].length(TargetHealthDescriptions))",
                 'value': 0,
                 'op': 'eq'}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_instance_count_filter_non_zero(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_instance_count_non_zero')
        p = self.load_policy({
            'name': 'appelb-instance-count-filter-non-zero',
            'resource': 'app-elb',
            'filters': [
                {'type': 'target-group',
                 'key': "max([].length(TargetHealthDescriptions))",
                 'value': 0,
                 'op': 'gt'}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_add_tag(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_add_tag')
        p = self.load_policy({
            'name': 'appelb-add-tag',
            'resource': 'app-elb',
            'filters': [
                {'type': 'value',
                 'key': 'LoadBalancerName',
                 'value': 'alb-1'}],
            'actions': [
                {'type': 'tag', 'key': 'KEY42', 'value': 'VALUE99'}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_remove_tag(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_remove_tag')
        p = self.load_policy({
            'name': 'appelb-remove-tag',
            'resource': 'app-elb',
            'filters': [
                {'type': 'value',
                 'key': 'LoadBalancerName',
                 'value': 'alb-1'}],
            'actions': [
                {'type': 'remove-tag', 'tags': ['KEY42']}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_mark_for_delete(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_mark_for_delete')
        p = self.load_policy({
            'name': 'appelb-mark-for-delete',
            'resource': 'app-elb',
            'filters': [
                {'type': 'value',
                 'key': 'LoadBalancerName',
                 'value': 'alb-1'}],
            'actions': [
                {'type': 'mark-for-op', 'op': 'delete',
                 'tag': 'custodian_next', 'days': 1}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_delete(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_delete')
        p = self.load_policy({
            'name': 'appelb-delete',
            'resource': 'app-elb',
            'filters': [
                {'type': 'value',
                 'key': 'LoadBalancerName',
                 'value': 'alb-2'}],
            'actions': [
                {'type': 'delete'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_delete_force(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_delete_force')
        client = session_factory().client('elbv2')
        p = self.load_policy({
            'name': 'appelb-modify-listener-policy',
            'resource': 'app-elb',
            'filters': [{
                'type': 'listener',
                'key': 'Port',
                'value': 80
            }],
            'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
            )
        resources = p.run()
        arn = resources[0]['LoadBalancerArn']
        attributes = client.describe_load_balancer_attributes(LoadBalancerArn=arn)['Attributes']
        for attribute in attributes:
            for key,value in attribute.iteritems():
                if 'deletion_protection.enabled' in key:
                    self.assertTrue(value)
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'appelb-modify-listener-policy',
            'resource': 'app-elb',
            'filters': [{
                'type': 'listener',
                'key': 'Port',
                'value': 80
            }],
            'actions': [{'type': 'delete', 'force': True}]
            },
            session_factory=session_factory
            )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class AppELBHealthcheckProtocolMismatchTest(BaseTest):

    def test_appelb_healthcheck_protocol_mismatch_filter_good(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_healthcheck_protocol_mismatch_good')
        p = self.load_policy({
            'name': 'appelb-healthcheck-protocol-mismatch-good',
            'resource': 'app-elb',
            'filters': ['healthcheck-protocol-mismatch']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_healthcheck_protocol_mismatch_filter_bad(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_healthcheck_protocol_mismatch_bad')
        p = self.load_policy({
            'name': 'appelb-healthcheck-protocol-mismatch-bad',
            'resource': 'app-elb',
            'filters': ['healthcheck-protocol-mismatch']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)


class AppELBTargetGroupTest(BaseTest):

    def test_appelb_target_group_simple(self):
        self.patch(AppELBTargetGroup, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_target_group_simple')
        p = self.load_policy({
            'name': 'appelb-target-group-simple',
            'resource': 'app-elb-target-group'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_appelb_target_group_simple_filter(self):
        self.patch(AppELBTargetGroup, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_target_group_simple')
        p = self.load_policy({
            'name': 'appelb-target-group-simple-filter',
            'resource': 'app-elb-target-group',
            'filters': [
                {'type': 'value',
                 'key': 'Port',
                 'value': 443}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appelb_target_group_default_vpc(self):
        self.patch(AppELBTargetGroup, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_appelb_target_group_default_vpc')
        p = self.load_policy({
            'name': 'appelb-target-group-default-vpc',
            'resource': 'app-elb-target-group',
            'filters': [{'type': 'default-vpc'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
