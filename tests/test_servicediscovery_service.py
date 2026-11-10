# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestServiceDiscoveryService(BaseTest):

    def test_servicediscovery_service(self):
        # Recording state: an HTTP namespace containing one service named
        # c7n-test-service tagged ASV=c7n-test.
        # session_factory = self.record_flight_data('test_servicediscovery_service')
        session_factory = self.replay_flight_data('test_servicediscovery_service')
        p = self.load_policy(
            {
                "name": "servicediscovery-service",
                "resource": "servicediscovery-service",
                "filters": [
                    {"Name": "c7n-test-service"},
                    {"tag:ASV": "c7n-test"}
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('NamespaceId', resources[0])
        self.assertEqual(p.resource_manager.get_arns(resources), [resources[0]['Arn']])

    def test_servicediscovery_service_delete(self):
        # Recording state: a service with no instances named c7n-delete-test-service.
        # session_factory = self.record_flight_data('test_servicediscovery_service_delete')
        session_factory = self.replay_flight_data('test_servicediscovery_service_delete')
        p = self.load_policy(
            {
                "name": "servicediscovery-service-delete",
                "resource": "servicediscovery-service",
                "filters": [{"Name": "c7n-delete-test-service"}],
                "actions": ["delete"]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('servicediscovery')
        names = [s['Name'] for s in client.list_services()['Services']]
        self.assertNotIn('c7n-delete-test-service', names)
