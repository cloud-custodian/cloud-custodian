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
import time
import unittest
import logging

from c7n.log import CloudWatchLogHandler
from .common import BaseTest


class LogTest(BaseTest):

    def test_existing_stream(self):
        session_factory = self.replay_flight_data('test_log_existing_stream')
        handler = CloudWatchLogHandler(session_factory=session_factory)
        log = logging.getLogger("custodian")
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(100, 115):
            log.info('hello world %s' % i)

        handler.flush()
        handler.close()

    def test_time_flush(self):
        session_factory = self.replay_flight_data('test_log_time_flush')
        log = logging.getLogger("test-c7n")
        handler = CloudWatchLogHandler(
            "test-maid-4", "alpha", session_factory=session_factory)
        handler.batch_interval = 1
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(100, 105):
            log.info('hello world %s' % i)

        time.sleep(1.1)
        log.info('bye world')
        self.assertFalse(handler.buf)
        handler.flush()
        handler.close()

    def test_transport_buffer_flush(self):
        session_factory = self.replay_flight_data(
            'test_transport_buffer_flush')
        log = logging.getLogger("test-c7n")
        handler = CloudWatchLogHandler(
            "test-maid-4", "alpha", session_factory=session_factory)
        handler.batch_size = 5
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(10):
            log.info("knock, knock %d" % i)

        handler.flush()
        self.assertFalse(handler.transport.buffers)
        

if __name__ == '__main__':
    unittest.main()
