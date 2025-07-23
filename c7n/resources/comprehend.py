# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeWithResourceTags
from c7n.filters import CrossAccountAccessFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.utils import local_session


@resources.register('comprehend-endpoint')
class ComprehendEndpoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_endpoints', 'EndpointPropertiesList', None)
        arn = id = 'EndpointArn'
        name = 'EndpointArn'
        date = 'CreationTime'
        universal_taggable = object()

    permissions = ('comprehend:ListEndpoints',)
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-entity-recognizer')
class ComprehendEntityRecognizer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_entity_recognizers', 'EntityRecognizerPropertiesList', None)
        arn = id = 'EntityRecognizerArn'
        name = 'EntityRecognizerArn'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = ('comprehend:ListEntityRecognizers',)
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-document-classifier')
class ComprehendDocumentClassifier(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_document_classifiers',
            'DocumentClassifierPropertiesList',
            None,
        )
        arn = id = 'DocumentClassifierArn'
        name = 'DocumentClassifierArn'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = ('comprehend:ListDocumentClassifiers',)
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-flywheel')
class ComprehendFlywheel(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_flywheels', 'FlywheelSummaryList', None)
        detail_spec = (
            'describe_flywheel',
            'FlywheelArn',
            'FlywheelArn',
            'FlywheelProperties',
        )
        arn = id = 'FlywheelArn'
        name = 'FlywheelArn'
        date = 'LastModifiedTime'
        universal_taggable = object()

    permissions = ('comprehend:ListFlywheels', 'comprehend:DescribeFlywheel')
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-entities-detection-job')
class ComprehendEntitiesDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_entities_detection_jobs',
            'EntitiesDetectionJobPropertiesList',
            None,
        )
        detail_spec = (
            'describe_entities_detection_job',
            'JobId',
            'JobId',
            'EntitiesDetectionJobProperties',
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListEntitiesDetectionJobs',
        'comprehend:DescribeEntitiesDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-sentiment-detection-job')
class ComprehendSentimentDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_sentiment_detection_jobs',
            'SentimentDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListSentimentDetectionJobs',
        'comprehend:DescribeSentimentDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-document-classification-job')
class ComprehendDocumentClassificationJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_document_classification_jobs',
            'DocumentClassificationJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListDocumentClassificationJobs',
        'comprehend:DescribeDocumentClassificationJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-topics-detection-job')
class ComprehendTopicsDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_topics_detection_jobs',
            'TopicsDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListTopicsDetectionJobs',
        'comprehend:DescribeTopicsDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-dominant-language-detection-job')
class ComprehendDominantLanguageDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_dominant_language_detection_jobs',
            'DominantLanguageDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListDominantLanguageDetectionJobs',
        'comprehend:DescribeDominantLanguageDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-key-phrases-detection-job')
class ComprehendKeyPhrasesDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_key_phrases_detection_jobs',
            'KeyPhrasesDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListKeyPhrasesDetectionJobs',
        'comprehend:DescribeKeyPhrasesDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-pii-entities-detection-job')
class ComprehendPiiEntitiesDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_pii_entities_detection_jobs',
            'PiiEntitiesDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListPiiEntitiesDetectionJobs',
        'comprehend:DescribePiiEntitiesDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-events-detection-job')
class ComprehendEventsDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_events_detection_jobs',
            'EventsDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListEventsDetectionJobs',
        'comprehend:DescribeEventsDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('comprehend-targeted-sentiment-detection-job')
class ComprehendTargetedSentimentDetectionJob(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = (
            'list_targeted_sentiment_detection_jobs',
            'TargetedSentimentDetectionJobPropertiesList',
            None,
        )
        arn = 'JobArn'
        id = 'JobId'
        name = 'JobName'
        date = 'SubmitTime'
        universal_taggable = object()

    permissions = (
        'comprehend:ListTargetedSentimentDetectionJobs',
        'comprehend:DescribeTargetedSentimentDetectionJob',
    )
    source_mapping = {'describe': DescribeWithResourceTags}


@ComprehendEntityRecognizer.filter_registry.register('cross-account')
@ComprehendDocumentClassifier.filter_registry.register('cross-account')
class ComprehendModelCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Checks for cross-account access in Comprehend model resource policies."""

    permissions = ('comprehend:DescribeResourcePolicy',)
    policy_annotation = "c7n:AccessPolicy"

    def get_resource_policy(self, r):
        client = local_session(self.manager.session_factory).client('comprehend')

        if self.policy_annotation in r:
            return r[self.policy_annotation]

        arn = r.get('EntityRecognizerArn') or r.get('DocumentClassifierArn')
        result = self.manager.retry(
            client.describe_resource_policy,
            ResourceArn=arn,
            ignore_err_codes=(
                'ResourceNotFoundException',
            ),
        )

        if result is not None:
            r[self.policy_annotation] = result['ResourcePolicy']
            return result['ResourcePolicy']

        return None


@ComprehendEntityRecognizer.filter_registry.register('kms-key')
@ComprehendDocumentClassifier.filter_registry.register('kms-key')
class ComprehendModelKmsFilter(KmsRelatedFilter):
    """Filter Comprehend models/recognizers by their KMS key."""

    RelatedIdsExpression = 'VolumeKmsKeyId'


@ComprehendFlywheel.filter_registry.register('kms-key')
class ComprehendFlywheelKmsFilter(KmsRelatedFilter):
    """Filter Comprehend flywheels by their KMS key."""

    RelatedIdsExpression = 'DataSecurityConfig.VolumeKmsKeyId'


@ComprehendEntitiesDetectionJob.filter_registry.register('kms-key')
@ComprehendSentimentDetectionJob.filter_registry.register('kms-key')
@ComprehendDocumentClassificationJob.filter_registry.register('kms-key')
@ComprehendTopicsDetectionJob.filter_registry.register('kms-key')
@ComprehendDominantLanguageDetectionJob.filter_registry.register('kms-key')
@ComprehendKeyPhrasesDetectionJob.filter_registry.register('kms-key')
@ComprehendPiiEntitiesDetectionJob.filter_registry.register('kms-key')
@ComprehendEventsDetectionJob.filter_registry.register('kms-key')
@ComprehendTargetedSentimentDetectionJob.filter_registry.register('kms-key')
class ComprehendJobKmsFilter(KmsRelatedFilter):
    """Filter Comprehend analysis jobs by their KMS key."""

    RelatedIdsExpression = 'OutputDataConfig.KmsKeyId'
