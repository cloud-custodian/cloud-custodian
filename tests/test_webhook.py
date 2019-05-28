# Copyright 2019 Microsoft Corporation
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

import mock

from c7n.actions.webhook import Webhook
from .common import BaseTest


class WebhookTest(BaseTest):

    def test_valid_policy(self):
        policy = {
            "name": "webhook-batch",
            "resource": "ec2",
            "actions": [
                {
                    "type": "webhook",
                    "url": "http://foo.com",
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

        policy = {
            "name": "webhook-batch",
            "resource": "ec2",
            "actions": [
                {
                    "type": "webhook",
                    "url": "http://foo.com",
                    "batch": True,
                    "parameters": {
                        "foo": "bar"
                    }
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

    @mock.patch('c7n.actions.webhook.request.urlopen')
    def test_process_batch(self, urlopen_mock):
        resources = [
            {
                "name": "test_name",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com",
            "batch": True,
            "parameters": {
                "foo": "[0].name"
            }
        }

        wh = Webhook(data=data)
        wh.process(resources)
        req = urlopen_mock.call_args[0][0]

        self.assertEqual("http://foo.com?foo=test_name", req.full_url)

    @mock.patch('c7n.actions.webhook.request.urlopen')
    def test_process_batch_body(self, urlopen_mock):
        resources = [
            {
                "name": "test_name",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com",
            "batch": True,
            "body": "[].name",
            "parameters": {
                "foo": "[0].name"
            }
        }

        wh = Webhook(data=data)
        wh.process(resources)
        req = urlopen_mock.call_args[0][0]

        self.assertEqual("http://foo.com?foo=test_name", req.full_url)
        self.assertEqual(b'["test_name"]', req.data)

    @mock.patch('c7n.actions.webhook.request.urlopen')
    def test_process_no_batch(self, urlopen_mock):
        resources = [
            {
                "name": "test1",
                "value": "test_value"
            },
            {
                "name": "test2",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com",
            "batch": False,
            "parameters": {
                "foo": "name"
            }
        }

        wh = Webhook(data=data)
        wh.process(resources)

        req1 = urlopen_mock.call_args_list[0][0][0]
        req2 = urlopen_mock.call_args_list[1][0][0]

        self.assertEqual("http://foo.com?foo=test1", req1.full_url)
        self.assertEqual("http://foo.com?foo=test2", req2.full_url)

    @mock.patch('c7n.actions.webhook.request.urlopen')
    def test_process_existing_query_string(self, urlopen_mock):
        resources = [
            {
                "name": "test1",
                "value": "test_value"
            },
            {
                "name": "test2",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com?existing=test",
            "batch": False,
            "parameters": {
                "foo": "name"
            }
        }

        wh = Webhook(data=data)
        wh.process(resources)

        req1 = urlopen_mock.call_args_list[0][0][0]
        req2 = urlopen_mock.call_args_list[1][0][0]

        self.assertEqual("http://foo.com?existing=test&foo=test1", req1.full_url)
        self.assertEqual("http://foo.com?existing=test&foo=test2", req2.full_url)
