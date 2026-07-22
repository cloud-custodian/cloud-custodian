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


class ResourceMessageBuffer:

    # conservative ratio calculated over all extant json test data
    # files, most resources have many common repeated keys and values
    # re compress down well.
    #
    # base64 increases size, but the compression still reduces total size versus raw.
    # https://lemire.me/blog/2019/01/30/what-is-the-space-overhead-of-base64-encoding/
    #
    # script to caculate ratio
    # https://gist.github.com/kapilt/8c3558a7db0d178cb1c4e91d47dacc77
    #
    # we use this conservative value as a seed and adapt based on observed data
    seed_b64_zlib_ratio = 0.5

    def __init__(self, envelope, buffer_max_size):
        self.buffer_max_size = buffer_max_size
        self.resource_parts = []

        envelope['resources'] = []
        self.envelope = utils.dumps(envelope)
        self.raw_size = float(len(self.envelope))
        self.observed_ratio = 0
        self.fill_sizes = []

    def add(self, resource):
        self.resource_parts.append(utils.dumps(resource))
        self.raw_size += len(self.resource_parts[-1])

    def __len__(self):
        return len(self.resource_parts)

    def __repr__(self):
        return (f"<ResourceBuffer count:{len(self)} esize:{self.estimated_size:.1f}"
                f" ratio:{self.compress_ratio:.2f} avg_rsize:{self.average_rsize:.1f}"
                f" fill:{self.fill_ratio:.2f}>")

    @property
    def fill_ratio(self):
        cardinality = float(len(self.fill_sizes) or 1)
        return sum(self.fill_sizes) / (self.buffer_max_size * cardinality)

    @property
    def estimated_size(self):
        return self.raw_size * self.compress_ratio

    @property
    def compress_ratio(self):
        return self.observed_ratio or self.seed_b64_zlib_ratio

    @property
    def average_rsize(self):
        rcount = len(self)
        if not rcount:
            return 0
        return (self.raw_size - len(self.envelope)) / float(rcount)

    @property
    def full(self):
        """ heuristic to calculate size of payload
        """
        if (self.raw_size + self.average_rsize * 2) * self.compress_ratio > self.buffer_max_size:
            return True
        return False

    def consume(self):
        rbegin_idx = self.envelope.rfind('[')
        rend_idx = self.envelope.rfind(']')

        payload = self.envelope
        payload = "%s%s%s" % (
            payload[:rbegin_idx + 1],
            ",".join(self.resource_parts),
            payload[rend_idx:]
        )

        serialized_payload = base64.b64encode(
            zlib.compress(
                payload.encode('utf8')
            )
        ).decode('ascii')

        if len(serialized_payload) > self.buffer_max_size:
            raise AssertionError(
                f"{self} payload over max size:{len(serialized_payload)}"
            )

        self.fill_sizes.append(len(serialized_payload))
        self.resource_parts = []
        # adapative ratio based on payload contents, with a static
        # increment for headroom on resource variance.
        self.observed_ratio = min(
            (len(serialized_payload) / float(self.raw_size)) + 0.1,
            self.seed_b64_zlib_ratio
        )
        self.raw_size = float(len(self.envelope))
        return serialized_payload


class BaseNotify(EventAction):

    message_buffer_class = ResourceMessageBuffer
    buffer_max_size = 262144

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
    an sqs queue, for processing.

    .. note::

       The ``notify`` action does not produce complete, human-readable messages
       on its own. Instead, the `c7n-mailer`_ tool renders and delivers
       messages by combining ``notify`` output with formatted templates.

       .. _c7n-mailer: ../../tools/c7n-mailer.html

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

        rbuffer = self.message_buffer_class(message, self.buffer_max_size)
        for r in self.prepare_resources(resources):
            rbuffer.add(r)
            if rbuffer.full:
                self.consume_buffer(message, rbuffer)

        if len(rbuffer):
            self.consume_buffer(message, rbuffer)

    def consume_buffer(self, message, rbuffer):
        rcount = len(rbuffer)
        payload = rbuffer.consume()
        receipt = self.send_data_message(message, payload)
        self.log.info("sent message:%s policy:%s template:%s count:%s" % (
            receipt, self.manager.data['name'],
            self.data.get('template', 'default'), rcount))

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

    def prepare_ecs_service(self, resources):
        for r in resources:
            r.pop('events', None)
        return resources

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

    def send_data_message(self, message, payload):
        if self.data['transport']['type'] == 'sqs':
            return self.send_sqs(message, payload)
        elif self.data['transport']['type'] == 'sns':
            return self.send_sns(message, payload)

    def send_sns(self, message, payload):
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
            Message=payload,
            MessageAttributes=attrs
        )
        return result['MessageId']

    def send_sqs(self, message, payload):
        queue = self.data['transport']['queue'].format(**message)
        domain = None
        if queue.startswith('https://'):
            domain = queue[len('https://'):].split('/', 1)[0]

        if queue.startswith('https://queue.amazonaws.com'):
            region = 'us-east-1'
            queue_url = queue
        elif domain and domain.endswith('queue.amazonaws.com'):
            region = domain.split('.', 1)[0]
            queue_url = queue
        elif domain and domain.startswith('sqs.'):
            region = domain.split('.', 2)[1]
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
            MessageBody=payload,
            MessageAttributes=attrs)
        return result['MessageId']

    @classmethod
    def register_resource(cls, registry, resource_class):
        if 'notify' in resource_class.action_registry:
            return

        resource_class.action_registry.register('notify', cls)


aws_resources.subscribe(Notify.register_resource)
