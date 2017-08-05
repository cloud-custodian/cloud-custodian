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

from c7n.resources.dynamodb import DeleteTable
from c7n.executor import MainThreadExecutor

class DynamodbTest(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data('test_dynamodb_table')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['TableName'], 'rolltop')
        self.assertEqual(resources[0]['TableStatus'], 'ACTIVE')

    def test_invoke_action(self):
        session_factory = self.replay_flight_data(
            'test_dynamodb_invoke_action')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table',
             'actions': [
                 {'type': 'invoke-lambda',
                  'function': 'process_resources'}
             ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_tables(self):
        session_factory = self.replay_flight_data('test_dynamodb_delete_table')
        self.patch(DeleteTable, 'executor_factory', MainThreadExecutor)
        p = self.load_policy({
            'name': 'delete-empty-tables',
            'resource': 'dynamodb-table',
            'filters': [{
                'TableSizeBytes': 0}],
            'actions': [{
                'type': 'delete'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(resources[0]['TableName'], 'c7n.DynamoDB.01')

    def test_tag_filter(self):
        session_factory = self.replay_flight_data('test_dynamodb_tag_filter')
        client = session_factory().client('dynamodb')
        p = self.load_policy({
            'name': 'dynamodb-tag-filters',
            'resource': 'dynamodb-table',
            'filters': [{
                'tag:test_key': 'test_value'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['TableArn']
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['Tags']}
        self.assertTrue('test_key' in tag_map)

    def test_dynamodb_mark(self):
        session_factory = self.replay_flight_data(
            'test_dynamodb_mark')
        client = session_factory().client('dynamodb')
        p = self.load_policy({
            'name': 'dynamodb-mark',
            'resource': 'dynamodb-table',
            'filters': [
                {'TableName': 'rolltop'}],
            'actions': [
                {'type': 'mark-for-op', 'days': 4,
                'op': 'delete', 'tag': 'test_tag'}]},
            session_factory=session_factory)
        resources = p.run()
        arn = resources[0]['TableArn']
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['Tags']}
        self.assertTrue('test_key' in tag_map)

    def test_dynamodb_tag(self):
        session_factory = self.replay_flight_data('test_dynamodb_tag')
        client = session_factory().client('dynamodb')
        p = self.load_policy({
                'name': 'dynamodb-tag-table',
                'resource': 'dynamodb-table',
                'filters': [{'TableName': 'rolltop'}],
                'actions': [{
                    'type': 'tag',
                    'tags': {'new_tag_key': 'new_tag_value'}
                }]
            },
            session_factory=session_factory)
        resources = p.run()
        arn = resources[0]['TableArn']
        tags = client.list_tags_of_resource(ResourceArn=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['Tags']}
        self.assertEqual({
                'test_key': 'test_value',
                'new_tag_key': 'new_tag_value'
            },
            tag_map)

    def test_dynamodb_unmark(self):
        session_factory = self.replay_flight_data(
            'test_dynamodb_unmark')
        client = session_factory().client('dynamodb')
        p = self.load_policy({
            'name': 'dynamodb-unmark',
            'resource': 'dynamodb-table',
            'filters': [
                {'TableName': 'rolltop'}],
            'actions': [
                {'type': 'remove-tag',
                 'tags': ['test_key']}]},
            session_factory=session_factory)
        resources = p.run()
        arn = resources[0]['TableArn']
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_of_resource(ResourceArn=arn)
        self.assertFalse('test_key' in tags)
