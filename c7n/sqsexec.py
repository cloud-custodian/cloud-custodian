# Copyright 2015-2017 Capital One Services, LLC
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

concurrent.futures implementation over sqs


Scatter/Gather or Map/Reduce style over two sqs queues.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import random
import logging
import inspect

from c7n import utils

from concurrent.futures import Executor, Future

log = logging.getLogger('custodian.sqsexec')


def named(o):
    assert inspect.isfunction(o)
    return "%s:%s" % (o.__module__, o.__name__)


def resolve(o):
    name, func = o.rsplit(':', 1)
    module = __import__(name, fromlist=[True])
    return getattr(module, func)


class SQSExecutor(Executor):

    def __init__(self, session_factory, map_queue, reduce_queue):
        self.session_factory = session_factory
        self.map_queue = map_queue
        self.reduce_queue = reduce_queue
        self.sqs = utils.local_session(self.session_factory).client('sqs')
        self.op_sequence = self.op_sequence_start = int(random.random() * 1000000)
        self.futures = {}

    def submit(self, func, *args, **kwargs):
        """Submit a function for serialized execution on sqs
        """
        self.op_sequence += 1
        self.sqs.send_message(
            QueueUrl=self.map_queue,
            MessageBody=utils.dumps({'args': args, 'kwargs': kwargs}),
            MessageAttributes={
                'sequence_id': {
                    'StringValue': str(self.op_sequence),
                    'DataType': 'Number'},
                'op': {
                    'StringValue': named(func),
                    'DataType': 'String',
                },
                'ser': {
                    'StringValue': 'json',
                    'DataType': 'String'}}
        )

        self.futures[self.op_sequence] = f = SQSFuture(
            self.op_sequence)
        return f

    def gather(self):
        """Fetch results from separate queue
        """
        limit = self.op_sequence - self.op_sequence_start
        results = MessageIterator(self.sqs, self.reduce_queue, limit)
        for m in results:
            # sequence_id from above
            msg_id = int(m['MessageAttributes']['sequence_id']['StringValue'])
            if (not msg_id > self.op_sequence_start or not msg_id <= self.op_sequence or
            msg_id not in self.futures):
                raise RuntimeError(
                    "Concurrent queue user from different "
                    "process or previous results")
            f = self.futures[msg_id]
            f.set_result(m)
            results.ack(m)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MessageIterator(object):

    msg_attributes = ['sequence_id', 'op', 'ser']

    def __init__(self, client, queue_url, limit=0, timeout=10):
        self.client = client
        self.queue_url = queue_url
        self.limit = limit or limit
        self.timeout = timeout
        self.messages = []

    def __iter__(self):
        return self

    def __next__(self):
        if self.messages:
            return self.messages.pop(0)
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            WaitTimeSeconds=self.timeout,
            MessageAttributeNames=self.msg_attributes)

        msgs = response.get('Messages', [])
        for m in msgs:
            self.messages.append(m)
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration()

    next = __next__  # back-compat

    def ack(self, m):
        self.client.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=m['ReceiptHandle'])


class SQSWorker(object):

    stopped = False

    def __init__(self, session_factory, map_queue, reduce_queue, limit=0):
        self.session_factory = session_factory
        self.client = utils.local_session(self.session_factory).client('sqs')
        self.receiver = MessageIterator(self.client, map_queue, limit)

    def run(self):
        for m in self.receiver:
            while not self.stopped:
                self.process_message(m)
                self.receiver.ack(m)

    def stop(self):
        self.stopped = True

    def process_message(self, m):
        msg = utils.loads(m['Body'])
        op_name = m['MessageAttributes']['op']['StringValue']
        func = resolve(op_name)

        try:
            func(*msg['args'], **msg['kwargs'])
        except Exception as e:
            log.exception(
                "Error invoking %s %s" % (
                    op_name, e))
            return


class SQSFuture(Future):

    marker = object()

    def __init__(self, sequence_id):
        super(SQSFuture, self).__init__()
        self.sequence_id = sequence_id
