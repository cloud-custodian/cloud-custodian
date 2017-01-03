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
import logging
import memcache
from processor import Processor

DATA_MESSAGE = "maidmsg/1.0"
EMAIL_MESSAGE = "email/1.0"

log = logging.getLogger('custodian.mailer')


class MessageIterator(object):
    # Copied from custodian to avoid runtime library dependency
    msg_attributes = ['sequence_id', 'op', 'ser']

    def __init__(self, client, queue_url, limit=0, timeout=10):
        self.client = client
        self.queue_url = queue_url
        self.limit = limit or limit
        self.timeout = timeout
        self.messages = []

    def __iter__(self):
        return self

    def ack(self, m):
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=m['ReceiptHandle'])

    def next(self):
        if self.messages:
            return self.messages.pop(0)
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            WaitTimeSeconds=self.timeout,
            MaxNumberOfMessages=3,
            MessageAttributeNames=self.msg_attributes)

        msgs = response.get('Messages', [])
        log.info("Messages received %d", len(msgs))
        for m in msgs:
            self.messages.append(m)
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration()


class Worker(object):

    def __init__(self, config, context, session):
        self.config = config
        self.context = context
        self.session = session
        self.receive_queue = self.config['queue_url']
        self.cache = None
        if self.config.get('cache'):
            self.cache = memcache.Client([self.config['cache']])
        self.processor = Processor(self.config, session, self.cache)

    def run(self):
        self.ses = self.session.client('ses')

        log.info("Queue poll loop")
        while True:
            sqs = self.session.client('sqs')
            messages = MessageIterator(sqs, self.receive_queue)
            messages.msg_attributes = ['mtype', 'recipient']

            for m in messages:
                log.debug(
                    "Message id: %s received %s" % (
                        m['MessageId'], m.get('MessageAttributes', '')))
                msg_kind = m.get('MessageAttributes', {}).get('mtype')
                if msg_kind:
                    msg_kind = msg_kind['StringValue']
                if msg_kind == DATA_MESSAGE:
                    self.processor.process_data_message(m)
                elif msg_kind == EMAIL_MESSAGE:
                    try:
                        self.ses.send_raw_email(RawMessage=m['Body'])
                    except Exception as e:
                        log.exception("Unable to send raw message")
                else:
                    log.warning("Unknown message format %s" % (m['Body'][:50]))
                log.info("Processed Message")
                messages.ack(m)

                # Save 120s for actually sending out emails if we're batching.
                # also want a clean exist at boundary instead of retrying
                # sqs message.
                remaining = self.context.get_remaining_time_in_millis()
                if remaining < 120 * 1000:
                    self.processor.flush()
                    log.info("Exiting deadline")
                    return
            log.info("Loop Complete / no messages")
            return
