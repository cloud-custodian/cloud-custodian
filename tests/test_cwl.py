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


class LogGroupTest(BaseTest):

    def test_last_write(self):
        factory = self.replay_flight_data('test_log_group_last_write')
        p = self.load_policy(
            {'name': 'stale-log-groups',
             'resource': 'log-group',
             'filters': [
                 {'type': 'last-write', 'days': 365}]
             },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['logGroupName'], 'obsolete')

    def test_retention(self):
        log_group = 'c7n-test-a'
        factory = self.replay_flight_data('test_log_group_retention')
        client = factory().client('logs')
        client.create_log_group(logGroupName=log_group)
        self.addCleanup(client.delete_log_group, logGroupName=log_group)
        p = self.load_policy(
            {'name': 'set-retention',
             'resource': 'log-group',
             'filters': [{
                 'logGroupName': log_group}],
             'actions': [
                 {'type': 'retention', 'days': 14}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            client.describe_log_groups(
                logGroupNamePrefix=log_group)['logGroups'][0]['retentionInDays'],
            14)

    def test_delete(self):
        log_group = 'c7n-test-b'
        factory = self.replay_flight_data('test_log_group_delete')
        client = factory().client('logs')
        client.create_log_group(logGroupName=log_group)

        p = self.load_policy(
            {'name': 'delete-log-group',
             'resource': 'log-group',
             'filters': [{
                 'logGroupName': log_group}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['logGroupName'], log_group)
        self.assertEqual(
            client.describe_log_groups(
                logGroupNamePrefix=log_group)['logGroups'], [])

    def test_add_tags(self):
        log_group = 'c7n-tagging-test'
        session_factory = self.replay_flight_data('test_log_group_tag')
        session = session_factory(region='us-east-1')
        client = session.client('logs')
        client.create_log_group(logGroupName=log_group)
        self.addCleanup(client.delete_log_group, logGroupName=log_group)

        p = self.load_policy({
            'name': 'tag-log-group',
            'resource': 'log-group',
            'filters': [{'logGroupName': log_group}],
            'actions': [{
                'type': 'tag',
                'key': 'RequiredTag',
                'value': 'TagValue'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            client.list_tags_log_group(logGroupName=log_group)['tags'],
            {'RequiredTag': 'TagValue'})

    def test_remove_tags(self):
        log_group = 'c7n-remove-tagging-test'
        session_factory = self.replay_flight_data('test_log_group_remove_tag')
        session = session_factory(region='us-east-1')
        client = session.client('logs')
        client.create_log_group(
            logGroupName=log_group, tags={'ExpiredTag': 'TagValue'})
        self.addCleanup(client.delete_log_group, logGroupName=log_group)

        tags = client.list_tags_log_group(logGroupName=log_group)['tags']
        self.assertEqual(tags, {'ExpiredTag': 'TagValue'})

        p = self.load_policy({
            'name': 'untag-log-group',
            'resource': 'log-group',
            'filters': [{'logGroupName': log_group}],
            'actions': [{
                'type': 'remove-tag',
                'tags': ['ExpiredTag']}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            len(client.list_tags_log_group(logGroupName=log_group)['tags']), 0)
