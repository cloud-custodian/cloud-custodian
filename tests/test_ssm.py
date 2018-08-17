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

from .common import BaseTest, functional


class TestSsm(BaseTest):

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
