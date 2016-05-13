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
"""
Actions to take on resources
"""
import base64
import logging
import zlib

from botocore.exceptions import ClientError

from c7n.registry import PluginRegistry
from c7n.executor import ThreadPoolExecutor
from c7n import utils


class ActionRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(ActionRegistry, self).__init__(*args, **kw)
        self.register('notify', Notify)

    def parse(self, data, manager):
        results = []
        for d in data:
            results.append(self.factory(d, manager))
        return results

    def factory(self, data, manager):
        if isinstance(data, dict):
            action_type = data.get('type')
            if action_type is None:
                raise ValueError(
                    "Invalid action type found in %s" % (data))
        else:
            action_type = data
            data = {}

        action_class = self.get(action_type)
        if action_class is None:
            raise ValueError(
                "Invalid action type %s, valid actions %s" % (
                    action_type, self.keys()))
        # Construct a ResourceManager
        return action_class(data, manager).validate()


class BaseAction(object):

    permissions = ()

    log = logging.getLogger("custodian.actions")

    executor_factory = ThreadPoolExecutor

    schema = {'type': 'object'}

    def __init__(self, data=None, manager=None, log_dir=None):
        self.data = data or {}
        self.manager = manager
        self.log_dir = log_dir

    def validate(self):
        return self

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def process(self, resources):
        raise NotImplemented(
            "Base action class does not implement behavior")

    def get_permissions(self):
        return self.permissions

    def _run_api(self, cmd, *args, **kw):
        try:
            return cmd(*args, **kw)
        except ClientError, e:
            if (e.response['Error']['Code'] == 'DryRunOperation'
                    and e.response['ResponseMetadata']['HTTPStatusCode'] == 412
                    and 'would have succeeded' in e.message):
                return self.log.info(
                    "Dry run operation %s succeeded" % (
                        self.__class__.__name__.lower()))
            raise


class EventAction(BaseAction):
    """Actions which receive lambda event if present
    """


class Notify(EventAction):
    """
    Flexible notifications require quite a bit of implementation support
    on pluggable transports, templates, address resolution, variable
    extraction, batch periods, etc.

    For expedience and flexibility then, we instead send the data to
    an sqs queue, for processing. ie. actual communications is DIY atm.

    Example::

      policies:
        - name: ec2-bad-instance-kill
          resource: ec2
          filters:
           - Name: bad-instance
          actions:
           - terminate
           - type: notify
             to:
              - event-user
              - resource-creator
              - email@address
             # which template for the email should we use
             template: policy-template
             transport:
               type: sqs
               region: us-east-1
               queue: xyz
    """

    C7N_DATA_MESSAGE = "maidmsg/1.0"

    schema = {
        'type': 'object',
        'required': ['type', 'transport', 'to'],
        'properties': {
            'type': {'enum': ['notify']},
            'to': {'type': 'array', 'items': {'type': 'string'}},
            'cc_manager': {'type': 'boolean'},
            'from': {'type': 'string'},
            'subject': {'type': 'string'},
            'template': {'type': 'string'},
            'transport': {
                'type': 'object',
                'required': ['type', 'queue'],
                'properties': {
                    'queue': {'type': 'string'},
                    'region': {'type': 'string'},
                    'type': {'enum': ['sqs']}}
            }
        }
    }

    def process(self, resources, event=None):
        for batch in utils.chunks(resources, 500):
            message = {'resources': batch,
                       'event': event,
                       'action': self.data,
                       'policy': self.manager.data}
            self.send_data_message(message)

    def send_data_message(self, message):
        if self.data['transport']['type'] == 'sqs':
            self.send_sqs(message)

    def send_sqs(self, message):
        queue = self.data['transport']['queue']
        region = self.data['transport'].get('region', 'us-east-1')
        client = self.manager.session_factory(region=region).client('sqs')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
                },
            }
        client.send_message(
            QueueUrl=queue,
            MessageBody=base64.b64encode(zlib.compress(utils.dumps(message))),
            MessageAttributes=attrs)
