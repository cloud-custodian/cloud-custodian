# Copyright 2018 Capital One Services, LLC
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

from c7n_gcp.mu import CloudFunction, CloudFunctionManager, HTTPEvent, custodian_archive

from gcp_common import BaseTest


class FunctionTest(BaseTest):

    def test_deploy_function(self):
        factory = self.replay_flight_data('mu-deploy')
        self.maxDiff = None
        config = dict(
            name="custodian-dev",
            labels=[],
            runtime='nodejs6',
            events=[HTTPEvent(factory)])
        archive = custodian_archive()
        func = CloudFunction(config, archive)
        manager = CloudFunctionManager(factory)
        manager.publish(func)
        func_info = manager.get(func.name)
        self.assertTrue(func_info['httpsTrigger'])
        self.assertEqual(func_info['status'], 'DEPLOY_IN_PROGRESS')
        self.assertEqual(
            func_info['name'],
            'projects/custodian-1291/locations/us-central1/functions/custodian-dev')
