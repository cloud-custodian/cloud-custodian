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

import logging
from c7n.actions import BaseNotify
from c7n import utils
from c7n.resolver import ValuesFrom
from c7n_gcp.provider import resources as gcp_resources
from c7n_gcp.pubsub_utils import PubSubUtilities

log = logging.getLogger('c7n_gcp.notify')


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
               location: us-central1
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
        return PubSubUtilities.publish_message(self.session, self.data, message)


gcp_resources.subscribe(
    gcp_resources.EVENT_FINAL, Notify.register_notify_action)
