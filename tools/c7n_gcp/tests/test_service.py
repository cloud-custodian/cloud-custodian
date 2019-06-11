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


class ServiceTest(BaseTest):

    def test_service_query(self):
        factory = self.replay_flight_data('service-query')
        p = self.load_policy(
            {'name': 'all-services',
             'resource': 'gcp.service'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 26)

    def test_service_disable(self):
        factory = self.replay_flight_data('service-disable')
        p = self.load_policy(
            {'name': 'disable-service',
             'resource': 'gcp.service',
             'filters': [
                 {'serviceName': 'deploymentmanager.googleapis.com'}],
             'actions': ['disable']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['serviceName'],
            'deploymentmanager.googleapis.com')

    def test_service_get(self):
        factory = self.replay_flight_data('service-get')
        p = self.load_policy(
            {'name': 'one-service', 'resource': 'gcp.service'},
            session_factory=factory)
        service = p.resource_manager.get_resource(
            {'resourceName': (
                'projects/604150802624/'
                'services/[deploymentmanager.googleapis.com]')})
        self.assertEqual(
            service, {
                'serviceName': 'deploymentmanager.googleapis.com'})
