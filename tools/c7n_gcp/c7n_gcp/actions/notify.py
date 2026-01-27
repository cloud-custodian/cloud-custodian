# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import BaseNotify
from c7n import utils
from c7n.resolver import ValuesFrom
from c7n_gcp.provider import resources as gcp_resources
from c7n.version import version


class Notify(BaseNotify):
    """
    :example:

    .. code-block:: yaml

          policies:
            - name: bad-instance-get
              resource: gcp.instance
              filters:
               - Name: bad-instance
              actions:
               - type: notify
                 to:
                  - email@address
                 # which template for the email should we use
                 template: policy-template
                 transport:
                   type: pubsub
                   topic: projects/yourproject/topics/yourtopic
    """

    batch_size = 1000

    schema = {
        'type': 'object',
        'addtionalProperties': False,
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
    schema_alias = True
    permissions = ('pubsub.topics.publish',)

    def process(self, resources, event=None):
        session = utils.local_session(self.manager.session_factory)
        client = session.client('pubsub', 'v1', 'projects.topics')

        project = session.get_default_project()
        message = {
            'event': event,
            'account_id': project,
            'account': project,
            'region': 'all',
            'policy': self.manager.data,
            'execution_id': self.manager.ctx.execution_id,
            'execution_start': self.manager.ctx.start_time,
            'version': version
        }

        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = batch
            self.publish_message(message, client)

    # Methods to handle GCP Pub Sub topic publishing
    def publish_message(self, message, client):
        """Publish message to a GCP pub/sub topic
         """
        return client.execute_command('publish', {
            'topic': self.data['transport']['topic'],
            'body': {
                'messages': {
                    'data': self.pack(message)
                }
            }
        })

    @classmethod
    def register_resource(cls, registry, resource_class):
        if resource_class.action_registry:
            resource_class.action_registry.register('notify', Notify)


gcp_resources.subscribe(Notify.register_resource)
