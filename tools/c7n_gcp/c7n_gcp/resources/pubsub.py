# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

"""
todo, needs detail_spec
"""


class PubSubTypeInfo(TypeInfo):
    service = 'pubsub'
    version = 'v1'
    scope_template = 'projects/{}'
    name = id = "name"
    urn_id_segments = (-1,)  # Just use the last segment of the id in the URN


@resources.register('pubsub-topic')
class PubSubTopic(QueryResourceManager):
    """GCP resource: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics
    """
    class resource_type(PubSubTypeInfo):
        component = 'projects.topics'
        enum_spec = ('list', 'topics[]', None)
        default_report_fields = ["name", "kmsKeyName"]
        asset_type = "pubsub.googleapis.com/Topic"
        metric_key = "resource.labels.topic_id"
        urn_component = "topic"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'topic': resource_info['topic_id']})


@PubSubTopic.filter_registry.register('iam-policy')
class PubSubTopicIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process pubsub topic resources correctly.
    """
    permissions = ('pubsub.topics.getIamPolicy',)


@PubSubTopic.action_registry.register('delete')
class DeletePubSubTopic(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        return {'topic': r['name']}


@resources.register('pubsub-subscription')
class PubSubSubscription(QueryResourceManager):
    """GCP resource: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions
    """
    class resource_type(PubSubTypeInfo):
        component = 'projects.subscriptions'
        enum_spec = ('list', 'subscriptions[]', None)
        default_report_fields = [
            "name", "topic", "ackDeadlineSeconds",
            "retainAckedMessages", "messageRetentionDuration"]
        asset_type = "pubsub.googleapis.com/Subscription"
        metric_key = 'resource.labels.subscription_id'
        urn_component = "subscription"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'subscription': resource_info['subscription_id']})


@PubSubSubscription.action_registry.register('delete')
class DeletePubSubSubscription(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        return {'subscription': r['name']}


@resources.register('pubsub-snapshot')
class PubSubSnapshot(QueryResourceManager):
    """GCP resource: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.snapshots
    """
    class resource_type(PubSubTypeInfo):
        component = 'projects.snapshots'
        enum_spec = ('list', 'snapshots[]', None)
        default_report_fields = [
            "name", "topic", "expireTime"]
        urn_component = "snapshot"
        asset_type = "pubsub.googleapis.com/Snapshot"


@PubSubSnapshot.action_registry.register('delete')
class DeletePubSubSnapshot(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        return {'snapshot': r['name']}
