# Copyright 2019 Capital One Services, LLC
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


class SpannerInstanceTest(BaseTest):
    def test_spanner_instance_query(self):
        project_id = 'atomic-shine-231410'
        session_factory = self.replay_flight_data('spanner-instance-query', project_id=project_id)

        policy = {
            'name': 'all-spanner-instances',
            'resource': 'gcp.spanner-instance'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['displayName'], 'test-instance')

    def test_spanner_instance_get(self):
        project_id = 'atomic-shine-231410'
        session_factory = self.replay_flight_data('spanner-instance-get', project_id=project_id)

        policy = {
            'name': 'one-spanner-instance',
            'resource': 'gcp.spanner-instance'
        }

        policy = self.load_policy(
            policy,
            session_factory=session_factory)

        instance = policy.resource_manager.get_resource(
            {'name': 'projects/atomic-shine-231410/instances/test-instance'})

        self.assertEqual(instance['state'], 'READY')
