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
from datetime import timedelta
import datetime

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

    def test_dynamodb_create_backup(self):
        dt = datetime.datetime.now().replace(
            year=2018, month=1, day=16, hour=19, minute=39)
        suffix = dt.strftime('%Y-%m-%d-%H-%M')

        session_factory = self.replay_flight_data(
            'test_dynamodb_create_backup')

        p = self.load_policy({
                'name': 'c7n-dynamodb-create-backup',
                'resource': 'dynamodb-table',
                'filters': [{'TableName': 'c7n-dynamodb-backup'}],
                'actions': [{
                    'type': 'backup'}]
            },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('dynamodb')
        arn = resources[0]['c7n:BackupArn']
        table = client.describe_backup(
            BackupArn=arn)
        self.assertEqual(table['BackupDescription']['BackupDetails']['BackupName'],
            'Backup-c7n-dynamodb-backup-%s' % (suffix))

    def test_dynamodb_create_prefixed_backup(self):
        dt = datetime.datetime.now().replace(
            year=2018, month=1, day=22, hour=13, minute=42)
        suffix = dt.strftime('%Y-%m-%d-%H-%M')

        session_factory = self.replay_flight_data(
            'test_dynamodb_create_prefixed_backup')

        p = self.load_policy({
            'name': 'c7n-dynamodb-create-prefixed-backup',
            'resource': 'dynamodb-table',
            'filters': [{'TableName': 'c7n-dynamodb-backup'}],
            'actions': [{
                'type': 'backup',
                'prefix': 'custom'}]
        },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('dynamodb')
        arn = resources[0]['c7n:BackupArn']
        table = client.describe_backup(
            BackupArn=arn)
        self.assertEqual(table['BackupDescription']['BackupDetails']['BackupName'],
                         'custom-c7n-dynamodb-backup-%s' % (suffix))

    def test_dynamodb_delete_backup(self):
        factory = self.replay_flight_data('test_dynamodb_delete_backup')
        p = self.load_policy({
            'name': 'c7n-dynamodb-delete-backup',
            'resource': 'dynamodb-backup',
            'filters': [{'TableName': 'omnissm-registrations'}],
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dynamodb_enable_stream(self):
        factory = self.replay_flight_data('test_dynamodb_enable_stream')
        p = self.load_policy({
            'name': 'c7n-dynamodb-enable-stream',
            'resource': 'dynamodb-table',
            'filters': [{'TableName': 'c7n-test'},
                        {'TableStatus': 'ACTIVE'}],
            'actions': [{
                'type': 'set-stream',
                'state': True,
                'stream_view_type': 'NEW_IMAGE'}]
        },
            session_factory=factory)
        resources = p.run()
        stream_field = resources[0]['c7n:StreamState']
        stream_type = resources[0]['c7n:StreamType']

        self.assertEqual(len(resources), 1)
        self.assertTrue(stream_field)
        self.assertEqual("NEW_IMAGE", stream_type)


class DynamoDbAccelerator(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data('test_dax_resources')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax'}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Status'], 'available')

    def test_dax_security_group(self):
        session_factory = self.replay_flight_data(
            'test_dax_security_group_filter')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{
                'type': 'security-group',
                'key': 'GroupName',
                'value': 'default'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')

    def test_tagging(self):
        session_factory = self.replay_flight_data(
            'test_dax_add_tags')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{'tag:Required': 'absent'}],
            'actions': [{
                'type': 'tag',
                'tags': {'Required': 'Required'}
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')
        client = session_factory(region='us-east-1').client('dax')
        tags = sorted(
            client.list_tags(ResourceName=resources[0]['ClusterArn'])['Tags'])
        self.assertEqual(tags[1]['Value'], 'Required')

    def test_remove_tagging(self):
        session_factory = self.replay_flight_data(
            'test_dax_remove_tags')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{'tag:Required': 'present'}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ['Required']
            }]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')
        client = session_factory(region='us-east-1').client('dax')
        tags = client.list_tags(ResourceName=resources[0]['ClusterArn'])['Tags']
        self.assertEqual(tags, [{'Key': 'Name', 'Value': 'c7n-dax-test'}])

    def test_mark_for_op(self):
        dtnow = datetime.datetime(year=2018, month=5, day=4, hour=16, minute=0)
        session_factory = self.replay_flight_data(
            'test_dax_mark_for_op')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [
                {'tag:custodian_cleanup': 'absent'},
                {'tag:Required': 'absent'}],
            'actions': [{
                'type': 'mark-for-op',
                'tag': 'custodian_cleanup',
                'msg': "Missing tag Required: {op}@{action_date}",
                'op': 'delete',
                'days': 7}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterName'], 'c7n-dax')
        client = session_factory(region='us-east-1').client('dax')
        dtact = (dtnow + timedelta(days=7)).strftime('%Y/%m/%d %H%M UTC')
        tags = sorted(
            client.list_tags(ResourceName=resources[0]['ClusterArn'])['Tags'])
        self.assertEqual(tags[1]['Value'],
                         'Missing tag Required: delete@%s' % dtact)

    def test_delete(self):
        session_factory = self.replay_flight_data(
            'test_dax_delete_cluster')
        p = self.load_policy({
            'name': 'dax-resources',
            'resource': 'dax',
            'filters': [{'tag:Required': 'absent'}],
            'actions': [{'type': 'delete'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory(region='us-east-1').client('dax')
        clusters = client.describe_clusters()['Clusters']
        self.assertEqual(clusters[0]['Status'], 'deleting')
