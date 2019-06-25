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


class OrganizationTest(BaseTest):

    def test_organization_query(self):
        organization_name = 'organizations/851339424791'
        session_factory = self.replay_flight_data('organization-query')

        policy = self.load_policy(
            {'name': 'gcp-organization-dryrun',
             'resource': 'gcp.organization'},
            session_factory=session_factory)

        organization_resources = policy.run()
        self.assertEqual(organization_resources[0]['name'], organization_name)


class FolderTest(BaseTest):

    def test_folder_query(self):
        resource_name = 'folders/112838955399'
        parent = 'organizations/926683928810'
        session_factory = self.replay_flight_data('folder-query')

        policy = self.load_policy(
            {'name': 'gcp-folder-dryrun',
             'resource': 'gcp.folder',
             'query':
                 [{'parent': parent}]},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(resources[0]['name'], resource_name)
        self.assertEqual(resources[0]['parent'], parent)
