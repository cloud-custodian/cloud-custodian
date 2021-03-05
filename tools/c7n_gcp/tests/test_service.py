# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class ServiceTest(BaseTest):

    def test_service_query(self):
        factory = self.replay_flight_data('service-query')
        p = self.load_policy(
            {'name': 'all-services',
             'resource': 'gcp.service'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 16)

    def test_service_disable(self):
        factory = self.replay_flight_data('service-disable')
        p = self.load_policy(
            {'name': 'disable-service',
             'resource': 'gcp.service',
             'filters': [
                 {'config.name': 'deploymentmanager.googleapis.com'}],
             'actions': ['disable']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertJmes('config.name', resources[0], 'deploymentmanager.googleapis.com')

    def test_service_get(self):
        factory = self.replay_flight_data('service-get')
        p = self.load_policy(
            {'name': 'one-service', 'resource': 'gcp.service'},
            session_factory=factory)
        service = p.resource_manager.get_resource(
            {'resourceName': 'projects/stacklet-sam/services/deploymentmanager.googleapis.com'})
        self.assertJmes('config.name', service, 'deploymentmanager.googleapis.com')
