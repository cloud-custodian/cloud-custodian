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
SQS Email Relay
===============

"""
import memcache
from sqs_message_processor import SqsMessageProcessor

DATA_MESSAGE = "maidmsg/1.0"


class MailerSqsQueueIterator(object):
    # Copied from custodian to avoid runtime library dependency
    msg_attributes = ['sequence_id', 'op', 'ser']

    def __init__(self, aws_sqs, queue_url, logger, limit=0, timeout=10):
        self.aws_sqs   = aws_sqs
        self.queue_url = queue_url
        self.limit     = limit or limit
        self.logger    = logger
        self.timeout   = timeout
        self.messages  = []

    # this and the next function make this object iterable with a for loop
    def __iter__(self):
        return self

    def ack(self, m):
        self.aws_sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=m['ReceiptHandle'])

    def next(self):
        if self.messages:
            return self.messages.pop(0)
        response = self.aws_sqs.receive_message(
            QueueUrl=self.queue_url,
            WaitTimeSeconds=self.timeout,
            MaxNumberOfMessages=3,
            MessageAttributeNames=self.msg_attributes)

        msgs = response.get('Messages', [])
        self.logger.info('Messages received %d', len(msgs))
        for m in msgs:
            self.messages.append(m)
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration()


class MailerSqsQueueProcessor(object):

    def __init__(self, config, session, logger):
        self.config        = config
        self.logger        = logger
        self.session       = session
        self.receive_queue = self.config['queue_url']
        self.cache         = None
        if self.config.get('cache'):
            self.cache = memcache.Client([self.config['cache']])
        self.sqs_message_processor = SqsMessageProcessor(self.config,
            session,self.cache, self.logger)

    def run(self):
        self.logger.info("Queue poll loop")
        while True:
            aws_sqs = self.session.client('sqs')
            sqs_messages = MailerSqsQueueIterator(aws_sqs, self.receive_queue, self.logger)
            sqs_messages.msg_attributes = ['mtype', 'recipient']
            for sqs_message in sqs_messages:
                self.logger.info(
                    "Message id: %s received %s" % (
                        sqs_message['MessageId'], sqs_message.get('MessageAttributes', '')))
                msg_kind = sqs_message.get('MessageAttributes', {}).get('mtype')
                if msg_kind:
                    msg_kind = msg_kind['StringValue']
                if msg_kind == DATA_MESSAGE:
                    self.sqs_message_processor.process_sqs_messsage(sqs_message)
                else:
                    warning_msg = 'Unknown sqs_message format %s' % (sqs_message['Body'][:50])
                    self.logger.warning(warning_msg)
                self.logger.info('Processed sqs_message')
                sqs_messages.ack(sqs_message)

            self.logger.info('Loop Complete / no sqs_messages')
            return
