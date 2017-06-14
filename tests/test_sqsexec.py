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
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import random
import string


from concurrent.futures import as_completed

from c7n.sqsexec import SQSExecutor, MessageIterator
from c7n import utils

from .common import BaseTest

TEST_SQS_PREFIX = os.environ.get("TEST_SQS_PREFIX", "cloud-c7n-test-sqsexec")


def int_processor(*args):
    if not args:
        return 1
    return args[0] * 2


class TestSQSExec(BaseTest):

    def test_sqsexec(self):
        session_factory = self.replay_flight_data('test_sqs_exec')
        client = session_factory().client('sqs')
        map_queue = client.create_queue(
            QueueName = "%s-map-%s" % (
                TEST_SQS_PREFIX, "".join(random.sample(string.letters, 3))))[
                    'QueueUrl']
        self.addCleanup(client.delete_queue, QueueUrl=map_queue)
        reduce_queue = client.create_queue(
            QueueName = "%s-map-%s" % (
                TEST_SQS_PREFIX, "".join(random.sample(string.letters, 3))))[
                    'QueueUrl']
        self.addCleanup(client.delete_queue, QueueUrl=reduce_queue)

        with SQSExecutor(
                session_factory, map_queue, reduce_queue) as w:
            w.op_sequence_start = 699723
            w.op_sequence = 699723
            # Submit work
            futures = []
            for i in range(10):
                futures.append(w.submit(int_processor, i))

            # Manually process and send results
            messages = MessageIterator(client, map_queue, limit=10)
            for m in messages:
                d = utils.loads(m['Body'])
                self.assertEqual(
                    m['MessageAttributes']['op']['StringValue'],
                    'tests.test_sqsexec:int_processor')
                client.send_message(
                    QueueUrl=reduce_queue,
                    MessageBody=utils.dumps([
                        d['args'], int_processor(*d['args'])]),
                    MessageAttributes=m['MessageAttributes'])
            w.gather()
            results = [json.loads(r.result()['Body'])
                       for r in list(as_completed(futures))]
            self.assertEqual(
                list(sorted(results))[-1],
                [[9], 18])
