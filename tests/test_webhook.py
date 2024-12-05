# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import json
from unittest import mock

from c7n.actions.webhook import Webhook
from c7n.exceptions import PolicyValidationError
from .common import BaseTest
import os


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
                    "query-params": {
                        "foo": "bar"
                    }
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

    def test_invalid_policy(self):
        # Missing URL parameter
        policy = {
            "name": "webhook-batch",
            "resource": "ec2",
            "actions": [
                {
                    "type": "webhook"
                }
            ],
        }

        with self.assertRaises(PolicyValidationError):
            self.load_policy(data=policy, validate=True)

        # Bad method
        policy = {
            "name": "webhook-batch",
            "resource": "ec2",
            "actions": [
                {
                    "type": "webhook",
                    "url": "http://foo.com",
                    "method": "CREATE"
                }
            ],
        }

        with self.assertRaises(PolicyValidationError):
            self.load_policy(data=policy, validate=True)

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
    def test_process_batch(self, request_mock):
        resources = [
            {
                "name": "test_name",
                "value": "test_value"
            },
            {
                "name": "test_name",
                "value": "test_value"
            },
            {
                "name": "test_name",
                "value": "test_value"
            },
            {
                "name": "test_name",
                "value": "test_value"
            },
            {
                "name": "test_name",
                "value": "test_value"
            }
        ]

        data = {
            "url": "http://foo.com",
            "batch": True,
            "batch-size": 2,
            "query-params": {
                "foo": "resources[0].name"
            }
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)
        req = request_mock.call_args[1]

        # 5 resources with max batch size 2 == 3 calls
        self.assertEqual(3, len(request_mock.call_args_list))

        # Check out one of the calls in detail
        self.assertEqual("http://foo.com?foo=test_name", req['url'])
        self.assertEqual("POST", req['method'])
        self.assertEqual({}, req['headers'])

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
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
                "test": "'header'"
            },
            "query-params": {
                "foo": "resources[0].name"
            }
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)
        req = request_mock.call_args[1]

        self.assertEqual("http://foo.com?foo=test_name", req['url'])
        self.assertEqual("POST", req['method'])
        self.assertEqual(b'[\n"test_name"\n]', req['body'])
        self.assertEqual(
            {"test": "header", "Content-Type": "application/json"},
            req['headers'])

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
    def test_process_date_serializer(self, request_mock):
        current = datetime.datetime.utcnow()
        resources = [
            {
                "name": "test1",
                "value": current
            },
        ]

        data = {
            "url": "http://foo.com",
            "body": "resources[]",
            'batch': True,
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)
        req1 = request_mock.call_args_list[0][1]
        self.assertEqual(
            json.loads(req1['body'])[0]['value'],
            current.isoformat())

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
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
            "query-params": {
                "foo": "resource.name"
            }
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)
        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertEqual("http://foo.com?foo=test1", req1['url'])
        self.assertEqual("http://foo.com?foo=test2", req2['url'])

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
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
            "query-params": {
                "foo": "resource.name"
            }
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)

        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertIn("existing=test", req1['url'])
        self.assertIn("foo=test1", req1['url'])
        self.assertIn("existing=test", req2['url'])
        self.assertIn("foo=test2", req2['url'])

    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
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
            "query-params": {
                "policy": "policy.name"
            }
        }

        wh = Webhook(data=data, manager=self._get_manager())
        wh.process(resources)
        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        self.assertEqual("http://foo.com?policy=webhook_policy", req1['url'])
        self.assertEqual("http://foo.com?policy=webhook_policy", req2['url'])

    @mock.patch('c7n.actions.webhook.urllib3.ProxyManager.request')
    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
    def test_process_with_http_proxy(self, pool_request_mock, proxy_request_mock):
        with mock.patch.dict(os.environ,
                             {'HTTP_PROXY': 'http://mock.http.proxy.server:8000'},
                             clear=True):
            resources = [
                {
                    "name": "test_name",
                    "value": "test_value"
                }
            ]

            data = {
                "url": "http://foo.com"
            }

            wh = Webhook(data=data, manager=self._get_manager())
            wh.process(resources)
            proxy_req = proxy_request_mock.call_args[1]

            self.assertEqual("http://foo.com", proxy_req['url'])
            self.assertEqual("POST", proxy_req['method'])

            self.assertEqual(1, proxy_request_mock.call_count)
            self.assertEqual(0, pool_request_mock.call_count)

    def _get_manager(self):
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
