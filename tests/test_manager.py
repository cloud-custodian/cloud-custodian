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
from c7n.resources.ec2 import EC2
from c7n.tags import Tag
from .common import BaseTest, instance, Bag, TestConfig as Config


class TestEC2Manager(BaseTest):

    def get_manager(self, data, config=None, session_factory=None):
        ctx = ExecutionContext(
            session_factory,
            Bag({'name':'test-policy'}),
            config or Config.empty())
        return EC2(ctx, data)

    def test_manager(self):
        ec2_mgr = self.get_manager(
            {'query': [
                {'tag-key': 'CMDBEnvironment'}],
             'filters': [
                 {'tag:ASV': 'absent'}]})
        self.assertEqual(len(ec2_mgr.filters), 1)
        self.assertEqual(len(ec2_mgr.queries), 1)
        self.assertEqual(
            ec2_mgr.resource_query(),
            [{'Values': ['CMDBEnvironment'], 'Name': 'tag-key'}])

    def test_filters(self):
        ec2 = self.get_manager({
            'filters': [
                {'tag:CMDBEnvironment': 'absent'}]})

        self.assertEqual(
            len(ec2.filter_resources([
                instance(Tags=[{"Key": "ASV", "Value": "xyz"}])])),
            1)

        self.assertEqual(
            len(ec2.filter_resources([
                instance(Tags=[{"Key": "CMDBEnvironment", "Value": "xyz"}])])),
            0)

    def test_actions(self):
        # a simple action by string
        ec2 = self.get_manager({'actions': ['mark']})
        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))

        # a configured action with dict
        ec2 = self.get_manager({
            'actions': [
                {'type': 'mark',
                 'msg': 'Missing proper tags'}]})
        self.assertEqual(len(ec2.actions), 1)
        self.assertTrue(isinstance(ec2.actions[0], Tag))
        self.assertEqual(ec2.actions[0].data,
                         {'msg': 'Missing proper tags', 'type': 'mark'})

