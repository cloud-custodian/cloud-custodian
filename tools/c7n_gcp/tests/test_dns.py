# Copyright 2018-2019 Capital One Services, LLC
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


class DnsManagedZoneTest(BaseTest):

    def test_managed_zone_query(self):
        project_id = 'cloud-custodian'
        managed_zone_name = 'custodian'
        session_factory = self.replay_flight_data(
            'managed-zone-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-managed-zone-dryrun',
             'resource': 'gcp.dns-managed-zone'},
            session_factory=session_factory)

        managed_zone_resources = policy.run()
        self.assertEqual(managed_zone_resources[0]['name'], managed_zone_name)

    def test_managed_zone_get(self):
        project_id = 'cloud-custodian'
        managed_zone_name = 'custodian'
        session_factory = self.replay_flight_data(
            'managed-zone-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-managed-zone-dryrun',
             'resource': 'gcp.dns-managed-zone'},
            session_factory=session_factory)

        managed_zone_resource = policy.resource_manager.get_resource(
            {'name': managed_zone_name, 'project_id': project_id})
        self.assertEqual(managed_zone_resource['name'], managed_zone_name)


class DnsPolicyTest(BaseTest):

    def test_policy_query(self):
        project_id = 'cloud-custodian'
        policy_name = 'custodian'
        session_factory = self.replay_flight_data(
            'policy-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-policy-dryrun',
             'resource': 'gcp.dns-policy'},
            session_factory=session_factory)

        policy_resources = policy.run()
        self.assertEqual(policy_resources[0]['name'], policy_name)

    def test_policy_get(self):
        project_id = 'cloud-custodian'
        policy_name = 'custodian'
        session_factory = self.replay_flight_data(
            'policy-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-dns-policy-dryrun',
             'resource': 'gcp.dns-policy'},
            session_factory=session_factory)

        policy_resource = policy.resource_manager.get_resource(
            {'name': policy_name, 'project_id': project_id})
        self.assertEqual(policy_resource['name'], policy_name)
