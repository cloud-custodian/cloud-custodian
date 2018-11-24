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
from c7n.manager import resources
from c7n.filters import FilterRegistry
from c7n.query import QueryResourceManager
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session


@resources.register('secrets-manager')
class SecretsManager(QueryResourceManager):
    filter_registry = FilterRegistry('secrets-manager.filters')
    filter_registry.register('marked-for-op', TagActionFilter)
    permissions = ('secretsmanager:ListSecretVersionIds',)

    class resource_type(object):
        service = 'secretsmanager'
        enum_spec = ('list_secrets', 'SecretList', None)
        detail_spec = ('describe_secret', 'SecretId', 'ARN', None)
        id = 'ARN'
        name = 'Name'
        dimension = None
        filter_name = None


@SecretsManager.action_registry.register('tag')
class TagSecretsManagerResource(Tag):
    """Action to create tag(s) on a Secret resource

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-secret
              resource: secrets-manager
              actions:
                - type: tag
                  key: tag-key
                  value: tag-value
    """

    permissions = ('secretsmanager:TagResource',)

    def process_resource_set(self, resources, new_tags):
        client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r['Tags']}
            for t in new_tags:
                tags[t['Key']] = t['Value']
            formatted_tags = [{'Key': k, 'Value': v} for k, v in tags.iteritems()]
            client.tag_resource(SecretId=r['ARN'], Tags=formatted_tags)


@SecretsManager.action_registry.register('remove-tag')
class RemoveTagSecretsManagerResource(RemoveTag):
    """Action to remove tag(s) on a Secret resource

    :example:

    .. code-block:: yaml

        policies:
            - name: untag-secret
              resource: secrets-manager
              actions:
                - type: remove-tag
                  tags: ['tag-to-be-removed']
    """

    permissions = ('secretsmanager:UntagResource',)

    def process_resource_set(self, resources, keys):
        client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            client.untag_resource(SecretId=r['ARN'], TagKeys=keys)


@SecretsManager.action_registry.register('mark-for-op')
class MarkSecretForOp(TagDelayedAction):
    """Action to mark a Secret resource for deferred action :example:

    .. code-block:: yaml

        policies:
            - name: mark-secret-for-delete
              resource: secrets-manager
              actions:
                - type: mark-for-op
                  op: delete
                  days: 1
    """

    permissions = ('secretsmanager:TagResource',)

    def process_resource_set(self, resources, new_tags):
        client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r['Tags']}
            for t in new_tags:
                tags[t['Key']] = t['Value']
            formatted_tags = [{'Key': k, 'Value': v} for k, v in tags.iteritems()]
            client.tag_resource(SecretId=r['ARN'], Tags=formatted_tags)
