# Copyright 2015-2018 Capital One Services, LLC
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

from googleapiclient.errors import HttpError
from gcp_common import BaseTest


class NotifyTest(BaseTest):

    def test_notify_schema_validate(self):
        factory = self.replay_flight_data('gcpnotifyvalidation')
        p = self.load_policy({
            'name': 'test-notify-for-gcpfunction',
            'resource': 'gcp.function',
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'pubsub',
                      'topic': 'testtopic'}
                 }
            ]}, validate=True, session_factory=factory)
        self.assertTrue(p)

    def test_pubsub_notify(self):
        factory = self.replay_flight_data("notify-action")
        session = factory()
        self.session = session
        self.topic_name = 'gcptestnotifytopic'
        self.project_id = self.session.get_default_project()
        # Create Temporary Topic
        topic = self.add_topic()

        p = self.load_policy({
            'name': 'test-notify',
            'resource': 'gcp.pubsub-topic',
            'filters': [
                {
                    'name': topic
                }
            ],
            'actions': [
                {'type': 'notify',
                 'template': 'default',
                 'priority_header': '2',
                 'subject': 'testing notify action',
                 'to': ['user@domain.com'],
                 'transport':
                     {'type': 'pubsub',
                      'topic': self.topic_name}
                 }
            ]}, session_factory=factory)
        resources = p.run()
        # Cleanup
        self.remove_topic()
        self.assertEqual(len(resources), 1)

    def add_topic(self):
        return self.ensure_topic()

    def remove_topic(self):
        client = self.session.client('pubsub', 'v1', 'projects.topics')
        client.execute_command('delete', {'topic': self.get_topic_param()})

    def get_topic_param(self, topic=None, project=None):
        """Returns Rest API URI formatted with topic and project in it
        """
        return 'projects/{}/topics/{}'.format(
            project or self.project_id,
            topic or self.topic_name)

    def ensure_topic(self):
        """Verify the pub/sub topic exists.
        If it does not, create it

        Returns the topic qualified name.
        """
        client = self.session.client('pubsub', 'v1', 'projects.topics')

        topic = self.get_topic_param()
        try:
            client.execute_command('get', {'topic': topic})
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return topic

        # bug in discovery doc.. apis say body must be empty but its required in the
        # discovery api for create.
        client.execute_command('create', {'name': topic, 'body': {}})
        return topic
