# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from c7n.utils import type_schema

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

"""
todo, needs detail_spec
"""


@resources.register('pubsub-topic')
class PubSubTopic(QueryResourceManager):
    """GCP resource: https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics
    """
    class resource_type(TypeInfo):
        service = 'pubsub'
        version = 'v1'
        component = 'projects.topics'
        enum_spec = ('list', 'topics[]', None)
        scope_template = "projects/{}"
        name = id = "name"
        default_report_fields = ["name", "kmsKeyName"]
        asset_type = "pubsub.googleapis.com/Topic"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'topic': resource_info['topic_id']})


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
    class resource_type(TypeInfo):
        service = 'pubsub'
        version = 'v1'
        component = 'projects.subscriptions'
        enum_spec = ('list', 'subscriptions[]', None)
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            "name", "topic", "ackDeadlineSeconds",
            "retainAckedMessages", "messageRetentionDuration"]
        asset_type = "pubsub.googleapis.com/Subscription"

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
    class resource_type(TypeInfo):
        service = 'pubsub'
        version = 'v1'
        component = 'projects.snapshots'
        enum_spec = ('list', 'snapshots[]', None)
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            "name", "topic", "expireTime"]


@PubSubSnapshot.action_registry.register('delete')
class DeletePubSubSnapshot(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        return {'snapshot': r['name']}
