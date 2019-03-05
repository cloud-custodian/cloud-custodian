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

import json
import logging
import mock
import os

from .common import BaseTest
from c7n.exceptions import PolicyExecutionError
from c7n.policy import Policy
from c7n import handler


class HandleTest(BaseTest):

    def test_get_local_output_dir(self):
        temp_dir = self.get_temp_dir()
        os.rmdir(temp_dir)
        self.change_environment(C7N_OUTPUT_DIR=temp_dir)
        self.assertEqual(
            handler.get_local_output_dir(), temp_dir)

    def test_init_config_exec_option_merge(self):
        policy_config = {
            'execution-options': {
                'region': 'us-east-1',
                'assume_role': 'arn:::',
                'profile': 'dev',
                'tracer': 'xray',
                'account_id': '004',
                'dryrun': True,
                'cache': '/foobar.cache'},
            'policies': [
                {'mode': {
                    'type': 'period',
                    'schedule': "rate(1 minute)",
                    'execution-options': {
                        'metrics_enabled': True,
                        'assume_role': 'arn::::007:foo',
                        'output_dir': 's3://mybucket/output'}},
                 'resource': 'aws.ec2',
                 'name': 'check-dev'}
            ]}
        self.assertEqual(
            dict(handler.init_config(policy_config)),
            {'assume_role': 'arn::::007:foo',
             'metrics_enabled': 'aws',
             'tracer': 'xray',
             'account_id': '007',
             'region': 'us-east-1',
             'output_dir': 's3://mybucket/output',

             # defaults
             'external_id': None,
             'dryrun': False,
             'profile': None,
             'authorization_file': None,
             'cache': '',
             'regions': (),
             'cache_period': 0,
             'log_group': None})

    def test_dispatch_log_event(self):
        self.patch(handler, 'policy_config', {'policies': []})
        output = self.capture_logging('custodian.lambda', level=logging.INFO)
        self.change_environment(C7N_DEBUG_EVENT=None)
        handler.dispatch_event({'detail': {'resource': 'xyz'}}, {})
        self.assertTrue('xyz' in output.getvalue())

        self.patch(handler, 'C7N_DEBUG_EVENT', False)
        handler.dispatch_event({'detail': {'resource': 'abc'}}, {})
        self.assertFalse('abc' in output.getvalue())

    @mock.patch('c7n.handler.PolicyCollection')
    def test_dispatch_err_event(self, mock_collection):
        self.patch(handler, 'policy_config', {
            'execution-options': {'output_dir': 's3://xyz', 'account_id': '004'},
            'policies': [{'resource': 'ec2', 'name': 'xyz'}]})
        mock_collection.from_data.return_value = []
        output = self.capture_logging('custodian.lambda', level=logging.DEBUG)
        handler.dispatch_event({'detail': {'errorCode': 'unauthorized'}}, None)
        self.assertTrue('Skipping failed operation: unauthorized' in output.getvalue())
        self.patch(handler, 'C7N_SKIP_EVTERR', False)
        handler.dispatch_event({'detail': {'errorCode': 'foi'}}, None)
        self.assertFalse('Skipping failed operation: foi' in output.getvalue())
        mock_collection.from_data.assert_called_once()

    @mock.patch('c7n.handler.PolicyCollection')
    def test_dispatch_err_handle(self, mock_collection):
        self.patch(handler, 'policy_config', {
            'execution-options': {'output_dir': 's3://xyz', 'account_id': '004'},
            'policies': [{'resource': 'ec2', 'name': 'xyz'}]})
        output = self.capture_logging('custodian.lambda', level=logging.WARNING)
        pmock = mock.MagicMock()
        pmock.push.side_effect = PolicyExecutionError("foo")
        mock_collection.from_data.return_value = [pmock]

        self.assertRaises(
            PolicyExecutionError,
            handler.dispatch_event,
            {'detail': {'xyz': 'oui'}}, None)

        self.patch(handler, 'C7N_CATCH_ERR', True)
        handler.dispatch_event({'detail': {'xyz': 'oui'}}, None)
        self.assertEqual(output.getvalue().count('error during'), 2)

    def test_handler(self):
        level = logging.root.level
        botocore_level = logging.getLogger("botocore").level

        self.run_dir = self.change_cwd()

        def cleanup():
            logging.root.setLevel(level)
            logging.getLogger("botocore").setLevel(botocore_level)

        self.addCleanup(cleanup)
        self.change_environment(C7N_OUTPUT_DIR=self.run_dir)

        policy_execution = []

        def push(self, event, context):
            policy_execution.append((event, context))

        self.patch(Policy, "push", push)

        from c7n import handler

        self.patch(handler, "account_id", "111222333444555")

        with open(os.path.join(self.run_dir, "config.json"), "w") as fh:
            json.dump(
                {
                    "policies": [
                        {
                            "resource": "asg",
                            "name": "autoscaling",
                            "filters": [],
                            "actions": [],
                        }
                    ]
                },
                fh,
            )

        self.assertEqual(
            handler.dispatch_event({"detail": {"errorCode": "404"}}, None), None
        )
        self.assertEqual(handler.dispatch_event({"detail": {}}, None), True)
        self.assertEqual(policy_execution, [({"detail": {}, "debug": True}, None)])

        config = handler.Config.empty()
        self.assertEqual(config.assume_role, None)
        try:
            config.foobar
        except AttributeError:
            pass
        else:
            self.fail("should have raised an error")
