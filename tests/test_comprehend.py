# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestComprehendEndpoint(BaseTest):

    def test_comprehend_endpoint_vpc(self):
        session_factory = self.replay_flight_data("test_comprehend_endpoint_vpc")
        p = self.load_policy(
            {
                "name": "list-comprehend-endpoints",
                "resource": "comprehend-endpoint",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('EndpointArn' in resources[0])
        self.assertTrue('VpcConfig' in resources[0])


class TestComprehendEntityRecognizer(BaseTest):
    def test_comprehend_entity_recognizer_vpc(self):
        session_factory = self.replay_flight_data("test_comprehend_entity_recognizer_vpc")
        p = self.load_policy(
            {
                "name": "list-comprehend-recognizers",
                "resource": "comprehend-entity-recognizer",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('EntityRecognizerArn' in resources[0])
        self.assertTrue('VpcConfig' in resources[0])


class TestComprehendDocumentClassifier(BaseTest):

    def test_comprehend_document_classifier_vpc(self):
        session_factory = self.replay_flight_data("test_comprehend_document_classifier_vpc")
        p = self.load_policy(
            {
                "name": "comprehend-document-classifier-vpc",
                "resource": "comprehend-document-classifier",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('VpcConfig' in resources[0])


class TestComprehendFlywheel(BaseTest):
    def test_comprehend_flywheel_vpc(self):
        session_factory = self.replay_flight_data("test_comprehend_flywheel_vpc")
        p = self.load_policy(
            {
                "name": "list-comprehend-flywheels",
                "resource": "comprehend-flywheel",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('FlywheelArn' in resources[0])
        self.assertTrue('VpcConfig' in resources[0])
