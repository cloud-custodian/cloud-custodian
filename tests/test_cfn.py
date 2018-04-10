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

from .common import BaseTest


class TestCFN(BaseTest):

    def test_delete(self):
        factory = self.replay_flight_data('test_cfn_delete')
        p = self.load_policy({
            'name': 'cfn-delete',
            'resource': 'cfn',
            'filters': [{'StackStatus': 'ROLLBACK_COMPLETE'}],
            'actions': ['delete']}, session_factory=factory)
        resources = p.run()
        self.maxDiff = None
        self.assertEqual(
            sorted([r['StackName'] for r in resources]),
            ['sphere11-db-1', 'sphere11-db-2', 'sphere11-db-3'])

    def test_query(self):
        factory = self.replay_flight_data('test_cfn_query')
        p = self.load_policy({
            'name': 'cfn-query',
            'resource': 'cfn'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources, [])

    def test_disable_protection(self):
        factory = self.replay_flight_data('test_cfn_disable_protection')
        client = factory().client('cloudformation')
        stacks = client.describe_stacks(
            StackName='mytopic').get('Stacks')
        self.assertEqual(stacks[0].get('EnableTerminationProtection'), True)
        p = self.load_policy({
            'name': 'cfn-disable-protection',
            'resource': 'cfn',
            'filters': [{'StackName': 'mytopic'}],
            'actions': [{
                'type': 'set-protection',
                'state': False}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('cloudformation')
        stacks = client.describe_stacks(
            StackName=resources[0]['StackName']).get('Stacks')
        self.assertEqual(stacks[0].get('EnableTerminationProtection'), False)

    def test_cfn_add_tag(self):
        session_factory = self.replay_flight_data('test_cfn_add_tag')
        p = self.load_policy({
            'name': 'cfn-add-tag',
            'resource': 'cfn',
            'filters': [{
                'tag:DesiredTag': 'absent'}],
            'actions': [{
                'type': 'tag',
                'key': 'DesiredTag',
                'value': 'DesiredValue'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('cloudformation')
        tags = client.describe_stacks(
            StackName=resources[0]['StackName'])['Stacks'][0]['Tags']
        self.assertEqual(
            [tags[0]['Key'], tags[0]['Value']], ['DesiredTag', 'DesiredValue'])

    def test_cfn_remove_tag(self):
        session_factory = self.replay_flight_data('test_cfn_remove_tag')
        p = self.load_policy({
            'name': 'cfn-remove-tag',
            'resource': 'cfn',
            'filters': [{'tag:DesiredTag': 'present'}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ['DesiredTag']}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region='us-east-1').client('cloudformation')
        tags = client.describe_stacks(
            StackName=resources[0]['StackName'])['Stacks'][0]['Tags']
        self.assertEqual(len(tags), 0)
