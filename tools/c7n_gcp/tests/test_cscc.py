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


class PostFinding(BaseTest):

    def test_cscc_post(self):
        factory = self.replay_flight_data(
            'cscc-post-finding', project_id='test-226520')
        session = factory()
        findings = session.client(
            'securitycenter', 'v1beta1', 'organizations.sources.findings')

        p = self.load_policy({
            'name': 'sketchy-drive',
            'resource': 'gcp.disk',
            'filters': [{'name': 'instance-1'}],
            'actions': [
                {'type': 'post-finding',
                 'org-domain': 'example.io'}
            ]},
            session_factory=factory)

        post_finding = p.resource_manager.actions[0]
        resources = p.run()
        self.assertEqual(len(resources), 1)
        resource = resources.pop()
        self.assertEqual(resource['name'], 'instance-1')

        source = post_finding.initialize_source()

        results = findings.execute_query(
            'list', {'parent': source}).get('findings', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]['sourceProperties']['resource-type'], 'disk')
