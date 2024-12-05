# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re
from unittest import mock

from .azure_common import BaseTest, arm_template
from c7n_azure.actions.logic_app import LogicAppAction
from c7n_azure.session import Session

from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session


class LogicAppTest(BaseTest):

    def test_valid_schema(self):
        assert 'url' not in LogicAppAction.schema['properties']

    def test_valid_policy(self):
        policy = {
            "name": "logic-app",
            "resource": "azure.vm",
            "actions": [
                {
                    "type": "logic-app",
                    "resource-group": "test_logic-app",
                    "logic-app-name": "cclogicapp"
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

        policy = {
            "name": "logic-app",
            "resource": "azure.vm",
            "actions": [
                {
                    "type": "logic-app",
                    "resource-group": "test_logic-app",
                    "logic-app-name": "cclogicapp",
                    "batch": True,
                    "query-params": {
                        "foo": "bar"
                    }
                }
            ],
        }

        self.assertTrue(self.load_policy(data=policy, validate=True))

    def test_invalid_policy(self):
        # Missing logic-app-name parameter
        policy = {
            "name": "logic-app",
            "resource": "azure.vm",
            "actions": [
                {
                    "type": "logic-app",
                    "resource-group": "test_logic-app"
                }
            ],
        }

        with self.assertRaises(PolicyValidationError):
            self.load_policy(data=policy, validate=True)

        # Extra URL parameter
        policy = {
            "name": "logic-app",
            "resource": "azure.vm",
            "actions": [
                {
                    "type": "logic-app",
                    "resource-group": "test_logic-app",
                    "url": "http://foo.com"
                }
            ],
        }

        with self.assertRaises(PolicyValidationError):
            self.load_policy(data=policy, validate=True)

    @arm_template('logic-app.json')
    @mock.patch('c7n.actions.webhook.urllib3.PoolManager.request')
    def test_get_callback(self, request_mock):
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

        suffix = local_session(Session).get_subscription_id()[-12:]
        data = {
            "resource-group": "test_logic-app",
            "logic-app-name": "cclogicapp{0}".format(suffix)
        }

        la = LogicAppAction(data=data, manager=self._get_manager())
        la.process(resources)
        req1 = request_mock.call_args_list[0][1]
        req2 = request_mock.call_args_list[1][1]

        regex = r'https://.*/workflows/.*/triggers/manual/paths/invoke' \
                + r'\?api-version=.*triggers%2Fmanual%2Frun'

        self.assertTrue(re.search(regex, req1['url']))
        self.assertTrue(re.search(regex, req2['url']))

    def _get_manager(self):
        """The tests don't require real resource data,
        but they do need a valid manager with
        policy metadata so we just make one here to use"""

        policy = self.load_policy({
            "name": "webhook_policy",
            "resource": "azure.vm",
            "actions": [
                {
                    "type": "logic-app",
                    "resource-group": "test_logic-app",
                    "logic-app-name": "cclogicapp"}
            ]})

        return policy.resource_manager
