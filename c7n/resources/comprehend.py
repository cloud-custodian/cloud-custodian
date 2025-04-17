# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.filters import CrossAccountAccessFilter
from c7n.utils import local_session
import json


class ComprehendEndpointDescribe(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('comprehend-endpoint')
class ComprehendEndpoint(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_endpoints', 'EndpointPropertiesList', None)
        arn = id = 'EndpointArn'
        name = 'EndpointArn'
        date = 'CreationTime'
        universal_taggable = object()

    source_mapping = {'describe': ComprehendEndpointDescribe}


class ComprehendEntityRecognizerDescribe(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('comprehend-entity-recognizer')
class ComprehendEntityRecognizer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'comprehend'
        enum_spec = ('list_entity_recognizers', 'EntityRecognizerPropertiesList', None)
        arn = id = 'EntityRecognizerArn'
        name = 'EntityRecognizerArn'
        date = 'SubmitTime'
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
        arn = id = 'DocumentClassifierArn'
        name = 'DocumentClassifierArn'
        date = 'SubmitTime'
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
        detail_spec = ('describe_flywheel', 'FlywheelArn', 'FlywheelArn', 'FlywheelProperties')
        arn = id = 'FlywheelArn'
        name = 'FlywheelArn'
        date = 'LastModifiedTime'
        universal_taggable = object()

    source_mapping = {'describe': ComprehendFlywheelDescribe}


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
        try:
            result = client.describe_resource_policy(ResourceArn=arn)
            policy_str = result.get('ResourcePolicy')

            if isinstance(policy_str, str):
                try:
                    policy = json.loads(policy_str)
                except json.JSONDecodeError:
                    policy = {}
            else:
                policy = policy_str or {}

        except client.exceptions.ResourceNotFoundException:
            policy = {}

        r[self.policy_annotation] = policy
        return policy
