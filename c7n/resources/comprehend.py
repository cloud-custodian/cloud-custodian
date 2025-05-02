# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeWithResourceTags
from c7n.filters import CrossAccountAccessFilter
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
        enum_spec = ('list_document_classifiers', 'DocumentClassifierPropertiesList', None)
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
        detail_spec = ('describe_flywheel', 'FlywheelArn', 'FlywheelArn', 'FlywheelProperties')
        arn = id = 'FlywheelArn'
        name = 'FlywheelArn'
        date = 'LastModifiedTime'
        universal_taggable = object()

    permissions = ('comprehend:ListFlywheels', 'comprehend:DescribeFlywheel')
    source_mapping = {'describe': DescribeWithResourceTags}


@ComprehendEntityRecognizer.filter_registry.register('cross-account')
@ComprehendDocumentClassifier.filter_registry.register('cross-account')
class ComprehendModelCrossAccountAccessFilter(CrossAccountAccessFilter):
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
            ignore_err_codes=('ResourceNotFoundException', 'PolicyNotFoundException'))

        if result is not None:
            r[self.policy_annotation] = result['ResourcePolicy']
            return result['ResourcePolicy']

        return None
