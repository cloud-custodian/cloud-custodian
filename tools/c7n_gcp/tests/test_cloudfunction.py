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

from gcp_common import BaseTest


class FunctionTest(BaseTest):

    def test_delete(self):
        factory = self.replay_flight_data(
            'function-delete', project_id='cloud-custodian')
        p = self.load_policy({
            'name': 'func-del',
            'resource': 'gcp.function',
            'filters': [
                {'httpsTrigger': 'present'},
                {'entryPoint': 'hello_http'}],
            'actions': ['delete']}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['status'], 'ACTIVE')
        client = p.resource_manager.get_client()
        func = client.execute_query(
            'get', {'name': resources[0]['name']})
        self.maxDiff = None
        self.assertEqual(func['status'], 'DELETE_IN_PROGRESS')
