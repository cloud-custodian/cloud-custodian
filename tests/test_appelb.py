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
from .common import BaseTest
from c7n.executor import MainThreadExecutor
from c7n.resources.appelb import AppELB

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

    def test_appelb_is_ssl_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_simple')
        p = self.load_policy({
            'name': 'appelb-is-ssl-filter',
            'resource': 'app-elb',
            'filters': ['is-ssl']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_appelb_default_vpc_filter(self):
        self.patch(AppELB, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_appelb_simple')
        p = self.load_policy({
            'name': 'appelb-default-vpc-filter',
            'resource': 'app-elb',
            'filters': ['default-vpc']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

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
        session_factory = self.replay_flight_data('test_appelb_mark_for_delete')
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
