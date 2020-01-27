# Copyright 2015-2017 Capital One Services, LLC
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

from c7n.ctx import ExecutionContext
from c7n.filters import Filter
from c7n.resources.ec2 import EC2
from c7n.tags import Tag
from .common import BaseTest, instance, Bag


class TestEC2Manager(BaseTest):

    def get_manager(self, data, config=None, session_factory=None):
        ctx = ExecutionContext(
            session_factory, Bag(
                {"name": "test-policy", 'provider_name': 'aws'}),
            config or {})
        return EC2(ctx, data)

    def test_manager_iter_filters(self):
        p = self.load_policy({
            'name': 'xyz',
            'resource': 'aws.app-elb',
            'filters': [
                {'and': [
                    {'type': 'listener',
                     'key': 'Protocol',
                     'value': 'HTTP'},
                    {'type': 'listener',
                     'key': 'DefaultActions[*].Type',
                     'op': 'ni',
                     'value_type': 'swap',
                     'value': 'redirect',
                     'matched': True}]}]})
        self.assertEqual(
            [f.type for f in p.resource_manager.iter_filters()],
            ['and', 'listener', 'listener'])

    def test_filter_get_block_op(self):
        class F(Filter):
            type = 'xyz'

        p = self.load_policy({
            'name': 'xyz',
            'resource': 'ec2',
            'filters': [
                {'and': [{'or': []}]},
                {'not': []},
                {'or': []}
            ]})

        m = p.resource_manager
        f = F({}, m)
        m.filters.append(f)
        self.assertEqual(f.get_block_operator(), 'and')

        f = F({}, m)
        m.filters[0].filters[0].filters.append(f)
        self.assertEqual(f.get_block_operator(), 'or')

        f = F({}, m)
        m.filters[1].filters.append(f)
        self.assertEqual(f.get_block_operator(), 'not')

    def test_get_resource_manager(self):
        p = self.load_policy(
            {'resource': 'ec2',
             'name': 'instances'})
        self.assertEqual(p.resource_manager.get_resource_manager(
            'aws.lambda').type, 'lambda')
        self.assertEqual(p.resource_manager.source_type, 'describe')
        self.assertRaises(
            ValueError,
            p.resource_manager.get_resource_manager,
            'gcp.lambda')

    def test_source_propagate(self):
        p = self.load_policy(
            {'resource': 'ec2',
             'source': 'config',
             'name': 'instances'})
        manager = p.resource_manager.get_resource_manager('aws.security-group')
        self.assertEqual(manager.source_type, 'config')

    def test_manager(self):
        ec2_mgr = self.load_policy({
            'name': 'xyz',
            'resource': 'aws.ec2',
            "query": [{"tag-key": "CMDBEnvironment"}],
            "filters": [{"tag:ASV": "absent"}]}
        ).resource_manager

        self.assertEqual(len(ec2_mgr.filters), 1)
        self.assertEqual(len(ec2_mgr.queries), 1)
        self.assertEqual(
            ec2_mgr.resource_query(),
            [{"Values": ["CMDBEnvironment"], "Name": "tag-key"}],
        )

    def test_filters(self):
        ec2 = self.load_policy({
            'name': 'xyz', 'resource': 'aws.ec2',
            'filters': [{"tag:CMDBEnvironment": "absent"}]}).resource_manager
        self.assertEqual(
            len(
                ec2.filter_resources([instance(Tags=[{"Key": "ASV", "Value": "xyz"}])])
            ),
            1,
        )

        self.assertEqual(
            len(
                ec2.filter_resources(
                    [instance(Tags=[{"Key": "CMDBEnvironment", "Value": "xyz"}])]
                )
            ),
            0,
        )

    def test_actions(self):
        # a simple action by string
        ec2 = self.load_policy(
            {'name': 'xyz', 'resource': 'aws.ec2',
             'actions': ['mark']}).resource_manager
        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))

        # a configured action with dict
        ec2 = self.load_policy(
            {'name': 'xyz', 'resource': 'aws.ec2',
             "actions": [
                 {"type": "mark",
                  "value": "Missing proper tags"}]}).resource_manager

        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))
        self.assertEqual(
            ec2.actions[0].data, {"value": "Missing proper tags", "type": "mark"}
        )
