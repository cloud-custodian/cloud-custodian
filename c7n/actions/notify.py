# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import base64
import copy
import zlib

from .core import EventAction
from c7n import utils
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources as aws_resources
from c7n.resolver import ValuesFrom
from c7n.version import version


class BaseNotify(EventAction):

    batch_size = 250

    def expand_variables(self, message):
        """expand any variables in the action to_from/cc_from fields.
        """
        p = copy.deepcopy(self.data)
        if 'to_from' in self.data:
            to_from = self.data['to_from'].copy()
            to_from['url'] = to_from['url'].format(**message)
            if 'expr' in to_from:
                to_from['expr'] = to_from['expr'].format(**message)
            p.setdefault('to', []).extend(ValuesFrom(to_from, self.manager).get_values())
        if 'cc_from' in self.data:
            cc_from = self.data['cc_from'].copy()
            cc_from['url'] = cc_from['url'].format(**message)
            if 'expr' in cc_from:
                cc_from['expr'] = cc_from['expr'].format(**message)
            p.setdefault('cc', []).extend(ValuesFrom(cc_from, self.manager).get_values())
        return p

    def pack(self, message):
        dumped = utils.dumps(message)
        compressed = zlib.compress(dumped.encode('utf8'))
        b64encoded = base64.b64encode(compressed)
        return b64encoded.decode('ascii')


class Notify(BaseNotify):
    """
    Flexible notifications require quite a bit of implementation support
    on pluggable transports, templates, address resolution, variable
    extraction, batch periods, etc.

    For expedience and flexibility then, we instead send the data to
    an sqs queue, for processing. ie. actual communications can be enabled
    with the c7n-mailer tool, found under tools/c7n_mailer.

    Attaching additional string message attributes are supported on the SNS
    transport, with the exception of the ``mtype`` attribute, which is a
    reserved attribute used by Cloud Custodian.

    :example:

    .. code-block:: yaml

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
                     owner_absent_contact:
                      - other_email@address
                     # which template for the email should we use
                     template: policy-template
                     transport:
                       type: sqs
                       region: us-east-1
                       queue: xyz
                - name: ec2-notify-with-attributes
                  resource: ec2
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
                       type: sns
                       region: us-east-1
                       topic: your-notify-topic
                       attributes:
                          attribute_key: attribute_value
                          attribute_key_2: attribute_value_2
    """

    C7N_DATA_MESSAGE = "maidmsg/1.0"

    schema_alias = True
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
                         'type': {'enum': ['sqs']}}},
                    {'type': 'object',
                     'required': ['type', 'topic'],
                     'properties': {
                         'topic': {'type': 'string'},
                         'type': {'enum': ['sns']},
                         'attributes': {'type': 'object'},
                     }}]
            },
            'assume_role': {'type': 'boolean'}
        }
    }

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Notify, self).__init__(data, manager, log_dir)
        self.assume_role = data.get('assume_role', True)

    def validate(self):
        if self.data.get('transport', {}).get('type') == 'sns' and \
                self.data.get('transport').get('attributes') and \
                'mtype' in self.data.get('transport').get('attributes').keys():
            raise PolicyValidationError(
                "attribute: mtype is a reserved attribute for sns transport")
        return self

    def get_permissions(self):
        if self.data.get('transport', {}).get('type') == 'sns':
            return ('sns:Publish',)
        if self.data.get('transport', {'type': 'sqs'}).get('type') == 'sqs':
            return ('sqs:SendMessage',)
        return ()

    def process(self, resources, event=None):
        alias = utils.get_account_alias_from_sts(
            utils.local_session(self.manager.session_factory))
        partition = utils.get_partition(self.manager.config.region)
        message = {
            'event': event,
            'account_id': self.manager.config.account_id,
            'partition': partition,
            'account': alias,
            'version': version,
            'region': self.manager.config.region,
            'execution_id': self.manager.ctx.execution_id,
            'execution_start': self.manager.ctx.start_time,
            'policy': self.manager.data}
        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = self.prepare_resources(batch)
            receipt = self.send_data_message(message)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def prepare_resources(self, resources):
        """Resources preparation for transport.

        If we have sensitive or overly large resource metadata we want to
        remove or additional serialization we need to perform, this
        provides a mechanism.

        TODO: consider alternative implementations, at min look at adding
        provider as additional discriminator to resource type. One alternative
        would be dynamically adjusting buffer size based on underlying
        transport.
        """
        handler = getattr(self, "prepare_%s" % (
            self.manager.type.replace('-', '_')),
            None)
        if handler is None:
            return resources
        return handler(resources)

    def prepare_launch_config(self, resources):
        for r in resources:
            r.pop('UserData', None)
        return resources

    def prepare_asg(self, resources):
        for r in resources:
            if 'c7n:user-data' in r:
                r.pop('c7n:user-data', None)
        return resources

    def prepare_ec2(self, resources):
        for r in resources:
            if 'c7n:user-data' in r:
                r.pop('c7n:user-data')
        return resources

    def prepare_iam_saml_provider(self, resources):
        for r in resources:
            if 'SAMLMetadataDocument' in r:
                r.pop('SAMLMetadataDocument')
            if 'IDPSSODescriptor' in r:
                r.pop('IDPSSODescriptor')
        return resources

    def send_data_message(self, message):
        if self.data['transport']['type'] == 'sqs':
            return self.send_sqs(message)
        elif self.data['transport']['type'] == 'sns':
            return self.send_sns(message)

    def send_sns(self, message):
        topic = self.data['transport']['topic'].format(**message)
        user_attributes = self.data['transport'].get('attributes')
        if topic.startswith('arn:'):
            region = region = topic.split(':', 5)[3]
            topic_arn = topic
        else:
            region = message['region']
            topic_arn = utils.generate_arn(
                service='sns', resource=topic,
                account_id=message['account_id'],
                region=message['region'])
        client = self.manager.session_factory(
            region=region, assume=self.assume_role).client('sns')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
            },
        }
        if user_attributes:
            for k, v in user_attributes.items():
                if k != 'mtype':
                    attrs[k] = {'DataType': 'String', 'StringValue': v}
        result = client.publish(
            TopicArn=topic_arn,
            Message=self.pack(message),
            MessageAttributes=attrs
        )
        return result['MessageId']

    def send_sqs(self, message):
        queue = self.data['transport']['queue'].format(**message)
        if queue.startswith('https://queue.amazonaws.com'):
            region = 'us-east-1'
            queue_url = queue
        elif 'queue.amazonaws.com' in queue:
            region = queue[len('https://'):].split('.', 1)[0]
            queue_url = queue
        elif queue.startswith('https://sqs.'):
            region = queue.split('.', 2)[1]
            queue_url = queue
        elif queue.startswith('arn:'):
            queue_arn_split = queue.split(':', 5)
            region = queue_arn_split[3]
            owner_id = queue_arn_split[4]
            queue_name = queue_arn_split[5]
            queue_url = "https://sqs.%s.amazonaws.com/%s/%s" % (
                region, owner_id, queue_name)
        else:
            region = self.manager.config.region
            owner_id = self.manager.config.account_id
            queue_name = queue
            queue_url = "https://sqs.%s.amazonaws.com/%s/%s" % (
                region, owner_id, queue_name)
        client = self.manager.session_factory(
            region=region, assume=self.assume_role).client('sqs')
        attrs = {
            'mtype': {
                'DataType': 'String',
                'StringValue': self.C7N_DATA_MESSAGE,
            },
        }
        result = client.send_message(
            QueueUrl=queue_url,
            MessageBody=self.pack(message),
            MessageAttributes=attrs)
        return result['MessageId']

    @classmethod
    def register_resource(cls, registry, resource_class):
        if 'notify' in resource_class.action_registry:
            return

        resource_class.action_registry.register('notify', cls)


aws_resources.subscribe(Notify.register_resource)
