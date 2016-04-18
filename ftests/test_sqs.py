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

import boto3
import json
import logging
import os
import random
import string
import unittest

from concurrent.futures import as_completed

from c7n.sqsexec import SQSExecutor, MessageIterator
from c7n import utils

TEST_SQS_PREFIX = os.environ.get("TEST_SQS_PREFIX", "cloud-c7n-ftest")


def session_factory():
    return boto3.Session()


def int_processor(*args):
    if not args:
        return 1
    return args[0] * 2


class SQSExecFunctional(unittest.TestCase):

    def setUp(self):
        logging.getLogger('botocore').setLevel(logging.WARNING)
        self.session = session_factory()
        self.client = self.session.client('sqs')
        self.map_queue = self.client.create_queue(
            QueueName = "%s-map-%s" % (
                TEST_SQS_PREFIX, "".join(random.sample(string.letters, 3))))[
                    'QueueUrl']
        self.addCleanup(self.client.delete_queue, QueueUrl=self.map_queue)
        self.reduce_queue = self.client.create_queue(
            QueueName = "%s-map-%s" % (
                TEST_SQS_PREFIX, "".join(random.sample(string.letters, 3))))[
                    'QueueUrl']
        self.addCleanup(self.client.delete_queue, QueueUrl=self.reduce_queue)        

    def test_executor_submit(self):
        with SQSExecutor(session_factory, self.map_queue, self.reduce_queue) as w:
            # Submit work
            futures = []
            for i in range(10):
                futures.append(w.submit(int_processor, i))

            # Manually process and send results
            messages = MessageIterator(self.client, self.map_queue, limit=10)
            for m in messages:
                d = utils.loads(m['Body'])
                self.assertEqual(
                    m['MessageAttributes']['op']['StringValue'],
                    'test_sqs:int_processor')
                self.client.send_message(
                    QueueUrl=self.reduce_queue,
                    MessageBody=utils.dumps([
                        d['args'], int_processor(*d['args'])]),
                    MessageAttributes=m['MessageAttributes'])
            w.gather()
            results = [json.loads(r.result()['Body'])
                       for r in list(as_completed(futures))]
            self.assertEqual(
                list(sorted(results))[-1],
                [[9], 18])
            
                

            
                
                
            

        
