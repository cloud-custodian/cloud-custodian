# Copyright 2018 Capital One Services, LLC
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

from googleapiclient.errors import HttpError
from c7n.actions import BaseNotify
from c7n import utils
from c7n.resolver import ValuesFrom
from c7n_gcp.provider import resources as gcp_resources


class Notify(BaseNotify):
    """Example:
        - name: gcp-notify-with-attributes
          resource: gcp-compute
          filters:
           - Name: bad-instance
          actions:
           - type: notify
             to:
              - event-user
              - resource-creator
              - email@address
             owner_absent_contact:
              - other_email@address
             # which template for the email should we use
             template: policy-template
             transport:
               type: pubsub
               topic: your-notify-topic
    """
    batch_size = 250

    schema = {
        'type': 'object',
        'anyOf': [
            {'required': ['type', 'transport', 'to']},
            {'required': ['type', 'transport', 'to_from']}],
        'properties': {
            'type': {'enum': ['notify']},
            'to': {'type': 'array', 'items': {'type': 'string'}},
            'owner_absent_contact': {'type': 'array', 'items': {'type': 'string'}},
            'to_from': ValuesFrom.schema,
            'cc': {'type': 'array', 'items': {'type': 'string'}},
            'cc_from': ValuesFrom.schema,
            'cc_manager': {'type': 'boolean'},
            'from': {'type': 'string'},
            'subject': {'type': 'string'},
            'template': {'type': 'string'},
            'transport': {
                'oneOf': [
                    {'type': 'object',
                     'required': ['type', 'topic'],
                     'properties': {
                         'topic': {'type': 'string'},
                         'type': {'enum': ['pubsub']},
                     }}],
            },
        }
    }

    @staticmethod
    def register_notify_action(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            klass.action_registry.register('notify', Notify)

    def process(self, resources, event=None):
        self.session = utils.local_session(self.manager.session_factory)
        project = self.session.get_default_project()
        message = {
            'event': event,
            'account_id': project,
            'account': project,
            'region': 'all',
            'policy': self.manager.data
        }

        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = batch
            receipt = self.send_data_message(message)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def send_data_message(self, message):
        return self.publish_message(message)

    # Methods to handle GCP Pub Sub topic publishing
    def publish_message(self, message):
        """Publish message to a GCP pub/sub topic
         """
        topic = self.ensure_topic()

        client = self.session.client('pubsub', 'v1', 'projects.topics')

        try:
            return client.execute_command('publish', {
                'topic': topic,
                'body': {
                    'messages': {
                        'data': self.pack(message)
                    }
                }
            })
        except HttpError as e:
            if e.resp.status != 404:
                raise

    def get_topic_param(self, topic=None, project=None):
        """Returns Rest API URI formatted with topic and project in it
        """
        return 'projects/{}/topics/{}'.format(
            project or self.session.get_default_project(),
            topic or self.data['transport']['topic'])

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


gcp_resources.subscribe(
    gcp_resources.EVENT_FINAL, Notify.register_notify_action)
