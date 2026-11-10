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

    def test_servicediscovery_service_instance(self):
        # Recording state: one service named c7n-test-service with two registered
        # instances, AWS_INSTANCE_IPV4=10.0.0.10 and AWS_INSTANCE_IPV4=203.0.113.10.
        # session_factory = self.record_flight_data('test_servicediscovery_service_instance')
        session_factory = self.replay_flight_data('test_servicediscovery_service_instance')
        p = self.load_policy(
            {
                "name": "servicediscovery-service-instance",
                "resource": "servicediscovery-service",
                "filters": [
                    {"Name": "c7n-test-service"},
                    {
                        "type": "instance",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "Attributes.AWS_INSTANCE_IPV4",
                                "op": "not-in",
                                "value_type": "cidr",
                                "value": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
                            }
                        ]
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:Instances']), 2)
        self.assertEqual(len(resources[0]['c7n:ListItemMatches']), 1)

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
