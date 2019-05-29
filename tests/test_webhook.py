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

    @mock.patch('c7n.actions.webhook.requests.Request')
    def test_process_batch(self, request_mock):
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
                "foo": "resources[0].name"
            }
        }

        wh = Webhook(data=data, manager=self.get_manager())
        wh.process(resources)
        req = request_mock.call_args[1]

        self.assertEqual("http://foo.com?foo=test_name", req['url'])
        self.assertEqual("GET", req['method'])
        self.assertEqual({}, req['headers'])

    @mock.patch('c7n.actions.webhook.requests.Request')
    def test_process_batch_body(self, request_mock):
        resources = [
            {
                "name": "test_name",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com",
            "batch": True,
            "body": "resources[].name",
            "body-size": 10,
            "headers": {
                "test": "`header`"
            },
            "parameters": {
                "foo": "resources[0].name"
            }
        }

        wh = Webhook(data=data, manager=self.get_manager())
        wh.process(resources)
        req = request_mock.call_args[1]

        self.assertEqual("http://foo.com?foo=test_name", req['url'])
        self.assertEqual("POST", req['method'])
        self.assertEqual(b'["test_name"]', req['data'])
        self.assertEqual(
            {"test": "header", "Content-Type": "application/json"},
            req['headers'])

    @mock.patch('c7n.actions.webhook.requests.Request')
    def test_process_no_batch(self, request_mock):
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
                "foo": "resource.name"
            }
        }

        wh = Webhook(data=data, manager=self.get_manager())
        wh.process(resources)
        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertEqual("http://foo.com?foo=test1", req1['url'])
        self.assertEqual("http://foo.com?foo=test2", req2['url'])

    @mock.patch('c7n.actions.webhook.requests.Request')
    def test_process_existing_query_string(self, request_mock):
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
                "foo": "resource.name"
            }
        }

        wh = Webhook(data=data, manager=self.get_manager())
        wh.process(resources)

        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertEqual("http://foo.com?existing=test&foo=test1", req1['url'])
        self.assertEqual("http://foo.com?existing=test&foo=test2", req2['url'])

    @mock.patch('c7n.actions.webhook.requests.Request')
    def test_process_policy_metadata(self, request_mock):
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
                "foo": "resource.name",
                "policy": "policy.name"
            }
        }

        wh = Webhook(data=data, manager=self.get_manager())
        wh.process(resources)
        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertEqual("http://foo.com?foo=test1&policy=webhook_policy", req1['url'])
        self.assertEqual("http://foo.com?foo=test2&policy=webhook_policy", req2['url'])

    def get_manager(self):
        """The tests don't require real resource data
        or recordings, but they do need a valid manager with
        policy metadata so we just make one here to use"""

        policy = self.load_policy({
            "name": "webhook_policy",
            "resource": "ec2",
            "actions": [
                {
                    "type": "webhook",
                    "url": "http://foo.com"}
            ]})

        return policy.resource_manager
