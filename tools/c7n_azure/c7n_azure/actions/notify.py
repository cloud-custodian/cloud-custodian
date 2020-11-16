# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.common import AzureHttpError

from c7n_azure.storage_utils import StorageUtilities

from c7n import utils
from c7n.actions import BaseNotify
from c7n.resolver import ValuesFrom


class Notify(BaseNotify):
    """
    Action to queue email.

    See `c7n_mailer readme.md <https://github.com/cloud-custodian/cloud-custodian/blob/
    master/tools/c7n_mailer/README.md#using-on-azure>`_ for more information.

    :example:

    .. code-block:: yaml

        policies:
          - name: notify
            resource: azure.resourcegroup
            actions:
              - type: notify
                template: default
                subject: Hello World
                to:
                  - someone@somewhere.com
                transport:
                  type: asq
                  queue: https://storagename.queue.core.windows.net/queuename
    """

    batch_size = 50

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
                     'required': ['type', 'queue'],
                     'properties': {
                         'queue': {'type': 'string'},
                         'type': {'enum': ['asq']}
                     }}],
            },
        }
    }
    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Notify, self).__init__(data, manager, log_dir)

    def process(self, resources, event=None):
        session = utils.local_session(self.manager.session_factory)
        subscription_id = session.get_subscription_id()
        message = {
            'event': event,
            'account_id': subscription_id,
            'account': subscription_id,
            'region': 'all',
            'policy': self.manager.data}

        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = batch
            receipt = self.send_data_message(message, session)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def send_data_message(self, message, session):
        if self.data['transport']['type'] == 'asq':
            queue_uri = self.data['transport']['queue']
            return self.send_to_azure_queue(queue_uri, message, session)

    def send_to_azure_queue(self, queue_uri, message, session):
        try:
            queue_service, queue_name = StorageUtilities.get_queue_client_by_uri(queue_uri, session)
            return StorageUtilities.put_queue_message(
                queue_service,
                queue_name,
                self.pack(message)).id
        except AzureHttpError as e:
            if e.status_code == 403:
                self.log.error("Access Error - Storage Queue Data Contributor Role is required "
                               "to enqueue messages to the Azure Queue Storage.")
            else:
                self.log.error("Error putting message to the queue.\n" +
                               str(e))
