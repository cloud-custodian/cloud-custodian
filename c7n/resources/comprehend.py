# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment


@resources.register('comprehend-endpoint')
class ComprehendEndpoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_endpoints', 'EndpointPropertiesList', None)
        detail_spec = ('describe_endpoint', 'EndpointArn', 'EndpointArn', None)
        arn = id = 'EndpointArn'
        name = 'EndpointArn'
        date = 'CreationTime'
        permission_prefix = 'comprehend'
        universal_taggable = object()


class ComprehendEntityRecognizerDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('comprehend-entity-recognizer')
class ComprehendEntityRecognizer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_entity_recognizers', 'EntityRecognizerPropertiesList', None)
        detail_spec = (
            'describe_entity_recognizer',
            'EntityRecognizerArn',
            'EntityRecognizerArn',
            None,
        )
        arn = id = 'EntityRecognizerArn'
        name = 'EntityRecognizerArn'
        date = 'SubmitTime'
        permission_prefix = 'comprehend'
        universal_taggable = object()

    source_mapping = {'describe': ComprehendEntityRecognizerDescribe}


class ComprehendDocumentClassifierDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('comprehend-document-classifier')
class ComprehendDocumentClassifier(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_document_classifiers', 'DocumentClassifierPropertiesList', None)
        detail_spec = (
            'describe_document_classifier',
            'DocumentClassifierArn',
            'DocumentClassifierArn',
            None,
        )
        arn = id = 'DocumentClassifierArn'
        name = 'DocumentClassifierArn'
        date = 'SubmitTime'
        permission_prefix = 'comprehend'
        universal_taggable = object()

    source_mapping = {'describe': ComprehendDocumentClassifierDescribe}


class ComprehendFlywheelDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('comprehend-flywheel')
class ComprehendFlywheel(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_flywheels', 'FlywheelSummaryList', None)
        detail_spec = ('describe_flywheel', 'FlywheelArn', 'FlywheelArn', None)
        arn = id = 'FlywheelArn'
        name = 'FlywheelArn'
        date = 'CreationTime'
        permission_prefix = 'comprehend'
        universal_taggable = object()

    source_mapping = {'describe': ComprehendFlywheelDescribe}
