# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class ComprehendEndpointTests(BaseTest):
    def test_comprehend_endpoint_tag_untag(self):
        session_factory = self.replay_flight_data("test_comprehend_endpoint_tag_untag")
        p = self.load_policy(
            {
                "name": "comprehend-endpoint-tags-find",
                "resource": "comprehend-endpoint",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client("comprehend")
        arn = resources[0]["EndpointArn"]
        client.untag_resource(ResourceArn=arn, TagKeys=["ASV"])

        p_after = self.load_policy(
            {
                "name": "comprehend-endpoint-tags-after",
                "resource": "comprehend-endpoint",
                "filters": [{"tag:ASV": "absent"}],
            },
            session_factory=session_factory,
        )
        resources_after = p_after.run()
        self.assertEqual(len(resources_after), 1)


class ComprehendEntityRecognizerTests(BaseTest):
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
        self.assertTrue("EntityRecognizerArn" in resources[0])
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_entity_recognizer_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_entity_recognizer_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "find-tagged-entity-recognizer",
                "resource": "comprehend-entity-recognizer",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1, "Should find one resource with the tag")

        p = self.load_policy(
            {
                "name": "untag-entity-recognizer",
                "resource": "comprehend-entity-recognizer",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()

        client = session_factory().client("comprehend")
        arn = resources[0]["EntityRecognizerArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertFalse(
            any(t.get("Key") == "ASV" for t in tags.get("Tags", [])),
            "Tag should be removed",
        )

    def test_comprehend_entity_recognizer_cross_account(self):
        factory = self.replay_flight_data("test_comprehend_entity_recognizer_cross_account")
        p = self.load_policy(
            {
                "name": "comprehend-entity-recognizer-cross-account",
                "resource": "comprehend-entity-recognizer",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_comprehend_entity_recognizer_kms_key(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_entity_recognizer_kms_key"
        )
        p = self.load_policy(
            {
                "name": "comprehend-entity-recognizer-kms",
                "resource": "comprehend-entity-recognizer",
                "filters": [{
                    'type': 'kms-key',
                    'key': 'c7n:AliasName',
                    'value': 'alias/comprehend-test-key'
                }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for resource in resources:
            self.assertTrue(resource["VolumeKmsKeyId"])


class ComprehendDocumentClassifierTests(BaseTest):
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
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_document_classifier_cross_account(self):
        factory = self.replay_flight_data(
            "test_comprehend_document_classifier_cross_account"
        )
        p = self.load_policy(
            {
                "name": "comprehend-document-classifier-cross-account",
                "resource": "comprehend-document-classifier",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_comprehend_document_classifier_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_document_classifier_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-document-classifier-tags",
                "resource": "comprehend-document-classifier",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["DocumentClassifierArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)

    def test_comprehend_document_classifier_kms_key(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_document_classifier_kms_key"
        )
        p = self.load_policy(
            {
                "name": "comprehend-document-classifier-kms",
                "resource": "comprehend-document-classifier",
                "filters": [{
                    'type': 'kms-key',
                    'key': 'c7n:AliasName',
                    'value': 'alias/comprehend-test-key'
                }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertGreater(len(resources), 0)
        for resource in resources:
            self.assertTrue(resource["VolumeKmsKeyId"])


class ComprehendFlywheelTests(BaseTest):
    def test_comprehend_flywheel_vpc(self):
        session_factory = self.replay_flight_data("test_comprehend_flywheel_vpc")
        p = self.load_policy(
            {
                "name": "list-comprehend-flywheels",
                "resource": "comprehend-flywheel",
                "filters": [
                    {
                        "type": "value",
                        "key": "DataSecurityConfig.VpcConfig",
                        "value": "present",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("FlywheelArn" in resources[0])
        self.assertTrue("DataSecurityConfig" in resources[0])
        self.assertTrue("VpcConfig" in resources[0]["DataSecurityConfig"])

    def test_comprehend_flywheel_tag_untag(self):
        session_factory = self.replay_flight_data("test_comprehend_flywheel_tag_untag")
        p = self.load_policy(
            {
                "name": "comprehend-flywheel-tags",
                "resource": "comprehend-flywheel",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["FlywheelArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)

    def test_comprehend_flywheel_kms_key(self):
        session_factory = self.replay_flight_data("test_comprehend_flywheel_kms_key")
        p = self.load_policy(
            {
                "name": "comprehend-flywheel-kms-check",
                "resource": "comprehend-flywheel",
                "filters": [{
                    'type': 'kms-key',
                    'key': 'c7n:AliasName',
                    'value': 'alias/comprehend-test-key'
                }],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["DataSecurityConfig"]["VolumeKmsKeyId"])

# Job Tests


class ComprehendEntitiesDetectionJobTests(BaseTest):
    def test_comprehend_entities_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_entities_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-entities-detection-job-vpc",
                "resource": "comprehend-entities-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_entities_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_entities_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-entities-detection-job-tags",
                "resource": "comprehend-entities-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendSentimentDetectionJobTests(BaseTest):
    def test_comprehend_sentiment_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_sentiment_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-sentiment-detection-job-vpc",
                "resource": "comprehend-sentiment-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_sentiment_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_sentiment_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-sentiment-detection-job-tags",
                "resource": "comprehend-sentiment-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendDocumentClassificationJobTests(BaseTest):
    def test_comprehend_document_classification_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_document_classification_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-document-classification-job-vpc",
                "resource": "comprehend-document-classification-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_document_classification_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_document_classification_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-document-classification-job-tags",
                "resource": "comprehend-document-classification-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendTopicsDetectionJobTests(BaseTest):
    def test_comprehend_topics_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_topics_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-topics-detection-job-vpc",
                "resource": "comprehend-topics-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_topics_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_topics_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-topics-detection-job-tags",
                "resource": "comprehend-topics-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendDominantLanguageDetectionJobTests(BaseTest):
    def test_comprehend_dominant_language_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_dominant_language_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-dominant-language-detection-job-vpc",
                "resource": "comprehend-dominant-language-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_dominant_language_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_dominant_language_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-dominant-language-detection-job-tags",
                "resource": "comprehend-dominant-language-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendKeyPhrasesDetectionJobTests(BaseTest):
    def test_comprehend_key_phrases_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_key_phrases_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-key-phrases-detection-job-vpc",
                "resource": "comprehend-key-phrases-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_key_phrases_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_key_phrases_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-key-phrases-detection-job-tags",
                "resource": "comprehend-key-phrases-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendPiiEntitiesDetectionJobTests(BaseTest):
    def test_comprehend_pii_entities_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_pii_entities_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-pii-entities-detection-job-tags",
                "resource": "comprehend-pii-entities-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendEventsDetectionJobTests(BaseTest):
    def test_comprehend_events_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_events_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-events-detection-job-tags",
                "resource": "comprehend-events-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)


class ComprehendTargetedSentimentDetectionJobTests(BaseTest):
    def test_comprehend_targeted_sentiment_detection_job_vpc(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_targeted_sentiment_detection_job_vpc"
        )
        p = self.load_policy(
            {
                "name": "comprehend-targeted-sentiment-detection-job-vpc",
                "resource": "comprehend-targeted-sentiment-detection-job",
                "filters": [{"type": "value", "key": "VpcConfig", "value": "present"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("VpcConfig" in resources[0])

    def test_comprehend_targeted_sentiment_detection_job_tag_untag(self):
        session_factory = self.replay_flight_data(
            "test_comprehend_targeted_sentiment_detection_job_tag_untag"
        )
        p = self.load_policy(
            {
                "name": "comprehend-targeted-sentiment-detection-job-tags",
                "resource": "comprehend-targeted-sentiment-detection-job",
                "filters": [{"tag:ASV": "PolicyTestASV"}],
                "actions": [{"type": "remove-tag", "tags": ["ASV"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("comprehend")
        arn = resources[0]["JobArn"]
        tags = client.list_tags_for_resource(ResourceArn=arn)
        self.assertEqual(len(tags.get("Tags", [])), 0)
