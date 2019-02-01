# Copyright 2017 Capital One Services, LLC
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

from c7n.exceptions import PolicyValidationError
from .common import BaseTest, functional

import time


class TestSsm(BaseTest):

    def test_ec2_ssm_send_command_validate(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'ssm-instances',
             'resource': 'aws.ec2',
             'actions': [
                 {'type': 'send-command',
                  'command': {
                      'DocumentName': 'AWS-RunShellScript'}}]},
            validate=True)

    def test_ssm_send_command(self):
        factory = self.replay_flight_data('test_ssm_send_command')
        p = self.load_policy({
            'name': 'ssm-instances',
            'resource': 'ssm-managed-instance',
            'filters': [{"PingStatus": "Online"}],
            'actions': [
                {'type': 'send-command',
                 'command': {
                     'DocumentName': 'AWS-RunShellScript',
                     'Parameters': {
                         'commands': [
                             'wget https://pkg.osquery.io/deb/osquery_3.3.0_1.linux.amd64.deb',
                             'dpkg -i osquery_3.3.0_1.linux.amd64.deb']}}}]},
            session_factory=factory, config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:SendCommand' in resources[0])

        if self.recording:
            time.sleep(5)

        result = factory().client('ssm').get_command_invocation(
            InstanceId=resources[0]['InstanceId'],
            CommandId=resources[0]['c7n:SendCommand'][0])
        self.assertEqual(result['Status'], 'Success')

    @functional
    def test_ssm_parameter_not_secure(self):
        session_factory = self.replay_flight_data("test_ssm_parameter_not_secure")
        client = session_factory().client("ssm")

        client.put_parameter(Name='test-name',
                             Type='String',
                             Overwrite=True,
                             Value='test-value')

        client.put_parameter(Name='secure-test-name',
                             Type='SecureString',
                             Overwrite=True,
                             Value='secure-test-value')

        p = self.load_policy(
            {
                "name": "ssm-parameter-not-secure",
                "resource": "ssm-parameter",
                "filters": [{"type": "value",
                             "op": "ne",
                             "key": "Type",
                             "value": "SecureString"}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.addCleanup(client.delete_parameters, Names=['test-name', 'secure-test-name'])

    def test_ssm_activation_expired(self):
        session_factory = self.replay_flight_data("test_ssm_activation_expired")
        p = self.load_policy(
            {
                "name": "ssm-list-expired-activations",
                "resource": "ssm-activation",
                "filters": [{"type": "value",
                             "key": "Expired",
                             "value": True}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_ssm_get_manager_instances(self):
        session_factory = self.replay_flight_data("test_ssm_get_managed_instances")
        p = self.load_policy(
            {
                "name": "ssm-get-managed-instances",
                "resource": "ssm-managed-instance"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "mi-1111aa111aa11a111")
