# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
import unittest
import logging

from c7n.log import CloudWatchLogHandler
from .common import BaseTest


class LogTest(BaseTest):

    def test_existing_stream(self):
        session_factory = self.replay_flight_data("test_log_existing_stream")
        client = session_factory().client("logs")
        group_name = "/custodian-dev"
        client.create_log_group(logGroupName=group_name)
        handler = CloudWatchLogHandler(group_name, session_factory=session_factory)
        log = logging.getLogger("custodian")
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(100, 115):
            log.info("hello world %s" % i)

        handler.flush()
        handler.close()

    def test_time_flush(self):
        session_factory = self.replay_flight_data("test_log_time_flush")
        log = logging.getLogger("test-c7n")
        handler = CloudWatchLogHandler(
            "test-c7n-4", "alpha", session_factory=session_factory
        )
        handler.batch_interval = 0.1
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(100, 105):
            log.info("hello world %s" % i)

        time.sleep(0.2)
        log.info("bye world")
        self.assertFalse(handler.buf)
        handler.flush()
        handler.close()

    def test_transport_buffer_flush(self):
        session_factory = self.replay_flight_data("test_transport_buffer_flush")
        log = logging.getLogger("test-c7n")
        handler = CloudWatchLogHandler(
            "test-c7n-5", "alpha", session_factory=session_factory
        )
        handler.batch_size = 5
        log.addHandler(handler)
        self.addCleanup(log.removeHandler, handler)
        log.setLevel(logging.DEBUG)

        for i in range(10):
            log.info("knock, knock %d" % i)

        handler.flush()
        self.assertFalse(handler.transport.buffers)


if __name__ == "__main__":
    unittest.main()
