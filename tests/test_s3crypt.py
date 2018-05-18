# Copyright 2016-2017 Capital One Services, LLC
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

import io
import json
import os
import tempfile
import mock

from unittest import TestCase

from c7n.resources import s3
from c7n.ufuncs import s3crypt
from .common import BaseTest
from six.moves.urllib_parse import quote_plus


class TestS3Crypt(TestCase):

    def setUp(self):
        self.old_dir = os.getcwd()
        os.chdir(tempfile.gettempdir())
        self.config_data = {"test": "data", "large": False}
        with open("config.json", "w") as conf:
            json.dump(self.config_data, conf)

    def tearDown(self):
        os.remove("config.json")
        os.chdir(self.old_dir)

    def test_init(self):
        s3crypt.init()
        self.assertEqual(s3crypt.config, self.config_data)

        # Run a second time to ensure it is idempotent
        s3crypt.init()
        self.assertEqual(s3crypt.config, self.config_data)


class TestS3CryptEvent(BaseTest):

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_s3_event_simple(self, mock_stdout):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt")
        client = session_factory().client("s3")
        self.patch(s3crypt, "s3", client)

        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": quote_plus("test-key"), "size": 42},
                    }
                }
            ]
        }
        s3crypt.process_event(event, {})

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_s3_event_unsafe_key(self, mock_stdout):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt")
        client = session_factory().client("s3")
        self.patch(s3crypt, "s3", client)

        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {
                            "key": quote_plus(
                                "/test000/!-_.*'()/&@:,$=+%2b?;/ /whatever"
                            ),
                            "size": 42,
                        },
                    }
                }
            ]
        }
        s3crypt.process_event(event, {})

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_s3_event_version(self, mock_stdout):
        self.patch(s3, "S3_AUGMENT_TABLE", [])
        session_factory = self.replay_flight_data("test_s3_encrypt")
        client = session_factory().client("s3")
        self.patch(s3crypt, "s3", client)

        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {
                            "key": quote_plus("test-key"), "size": 42, "versionId": "99"
                        },
                    }
                }
            ]
        }
        s3crypt.process_event(event, {})
