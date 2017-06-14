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
Python Standard Logging integration with CloudWatch Logs

Double Buffered with background thread delivery.

We do an initial buffering on the log handler directly, to avoid
some of the overhead of pushing to the queue (albeit dubious as
std logging does default lock acquisition around handler emit).
also uses a single thread for all outbound. Background thread
uses a separate session.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import boto3
from botocore.exceptions import ClientError

import itertools
import logging
from operator import itemgetter
import threading
import time

try:
    import Queue
except ImportError:  # pragma: no cover
    import queue as Queue

from c7n.utils import get_retry

FLUSH_MARKER = object()
SHUTDOWN_MARKER = object()

EMPTY = Queue.Empty


class Error(object):

    AlreadyAccepted = "DataAlreadyAcceptedException"
    InvalidToken = "InvalidSequenceTokenException"
    ResourceExists = "ResourceAlreadyExistsException"

    @staticmethod
    def code(e):
        return e.response.get('Error', {}).get('Code')


class CloudWatchLogHandler(logging.Handler):
    """Python Log Handler to Send to Cloud Watch Logs

    http://goo.gl/eZGAEK
    """

    batch_size = 20
    batch_interval = 40
    batch_min_buffer = 10

    def __init__(self, log_group=__name__, log_stream=None,
                 session_factory=None):
        super(CloudWatchLogHandler, self).__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.session_factory = session_factory or boto3.Session
        self.transport = None
        self.queue = Queue.Queue()
        self.threads = []
        # do some basic buffering before sending to transport to minimize
        # queue/threading overhead
        self.buf = []
        self.last_seen = time.time()
        # Logging module internally is tracking all handlers, for final
        # cleanup atexit, custodian is a bit more explicitly scoping shutdown to
        # each policy, so use a sentinel value to avoid deadlocks.
        self.shutdown = False
        retry = get_retry(('ThrottlingException',))
        try:
            client = self.session_factory().client('logs')
            logs = retry(
                client.describe_log_groups,
                logGroupNamePrefix=self.log_group)['logGroups']
            if not [l for l in logs if l['logGroupName'] == self.log_group]:
                retry(client.create_log_group,
                      logGroupName=self.log_group)
        except ClientError as e:
            if Error.code(e) != Error.ResourceExists:
                raise

    # Begin logging.Handler API
    def emit(self, message):
        """Send logs"""
        # We're sending messages asynchronously, bubble to caller when
        # we've detected an error on the message. This isn't great,
        # but options once we've gone async without a deferred/promise
        # aren't great.
        if self.transport and self.transport.error:
            raise self.transport.error

        # Sanity safety, people do like to recurse by attaching to
        # root log :-(
        if message.name.startswith('boto'):
            return

        msg = self.format_message(message)
        if not self.transport:
            self.start_transports()
        self.buf.append(msg)
        self.flush_buffers(
            (message.created - self.last_seen >= self.batch_interval))

        self.last_seen = message.created

    def flush(self):
        """Ensure all logging output has been flushed."""
        if self.shutdown:
            return
        self.flush_buffers(force=True)
        self.queue.put(FLUSH_MARKER)
        self.queue.join()

    def close(self):
        if self.shutdown:
            return
        self.shutdown = True
        self.queue.put(SHUTDOWN_MARKER)
        self.queue.join()
        for t in self.threads:
            t.join()
        self.threads = []

    # End logging.Handler API

    def format_message(self, msg):
        """format message."""
        return {'timestamp': int(msg.created * 1000),
                'message': self.format(msg),
                'stream': self.log_stream or msg.name,
                'group': self.log_group}

    def start_transports(self):
        """start thread transports."""
        self.transport = Transport(
            self.queue, self.batch_size, self.batch_interval,
            self.session_factory)
        thread = threading.Thread(target=self.transport.loop)
        self.threads.append(thread)
        thread.daemon = True
        thread.start()

    def flush_buffers(self, force=False):
        if not force and len(self.buf) < self.batch_min_buffer:
            return
        self.queue.put(self.buf)
        self.buf = []


class Transport(object):

    def __init__(self, queue, batch_size, batch_interval, session_factory):
        self.queue = queue
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.client = session_factory().client('logs')
        self.sequences = {}
        self.buffers = {}
        self.error = None

    def create_stream(self, group, stream):
        try:
            self.client.create_log_stream(
                logGroupName=group, logStreamName=stream)
        except ClientError as e:
            if Error.code(e) != Error.ResourceExists:
                self.error = e
                return False
        return True

    def send(self):
        for k, messages in self.buffers.items():
            self.send_group(k, messages)
        self.buffers = {}

    def send_group(self, k, messages):
        group, stream = k.split('=', 1)
        if stream not in self.sequences:
            if not self.create_stream(group, stream):
                return
            self.sequences[stream] = None
        params = dict(
            logGroupName=group, logStreamName=stream,
            logEvents=sorted(
                messages, key=itemgetter('timestamp'), reverse=False))
        if self.sequences[stream]:
            params['sequenceToken'] = self.sequences[stream]
        try:
            response = self.client.put_log_events(**params)
        except ClientError as e:
            if Error.code(e) in (Error.AlreadyAccepted, Error.InvalidToken):
                self.sequences[stream] = e.response['Error']['Message'].rsplit(
                    " ", 1)[-1]
                return self.send_group(k, messages)
            self.error = e
            return
        self.sequences[stream] = response['nextSequenceToken']

    def loop(self):
        def keyed(datum):
            return "%s=%s" % (
                datum.pop('group'), datum.pop('stream'))

        while True:
            try:
                datum = self.queue.get(block=True, timeout=self.batch_interval)
            except EMPTY:
                if Queue is None:
                    return
                datum = None
            if datum is None:
                # Timeout reached, flush
                self.send()
                continue
            elif datum == FLUSH_MARKER:
                self.send()
            elif datum == SHUTDOWN_MARKER:
                self.queue.task_done()
                return
            else:
                for k, group in itertools.groupby(datum, keyed):
                    self.buffers.setdefault(k, []).extend(group)
            self.queue.task_done()
