# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.filters import iamaccess
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session


@resources.register('secrets-manager')
class SecretsManager(QueryResourceManager):

    permissions = ('secretsmanager:ListSecretVersionIds',)

    class resource_type(TypeInfo):
        service = 'secretsmanager'
        enum_spec = ('list_secrets', 'SecretList', None)
        detail_spec = ('describe_secret', 'SecretId', 'Name', None)
        cfn_type = 'AWS::SecretsManager::Secret'
        name = id = 'Name'
        arn = 'ARN'


SecretsManager.filter_registry.register('marked-for-op', TagActionFilter)


@SecretsManager.filter_registry.register('cross-account')
class CrossAccountAccessFilter(iamaccess.CrossAccountAccessFilter):

    policy_annotation = "c7n:AccessPolicy"
    permissions = ("secretsmanager:GetResourcePolicy",)

    def process(self, resources, event=None):
        self.client = local_session(self.manager.session_factory).client('secretsmanager')
        return super(CrossAccountAccessFilter, self).process(resources)

    def get_resource_policy(self, r):
        if self.policy_annotation in r:
            return r[self.policy_annotation]
        r[self.policy_annotation] = p = self.client.get_resource_policy(
            SecretId=r['Name']).get('ResourcePolicy', None)
        return p


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

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r['Tags']}
            for t in new_tags:
                tags[t['Key']] = t['Value']
            formatted_tags = [{'Key': k, 'Value': v} for k, v in tags.items()]
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

    def process_resource_set(self, client, resources, keys):
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
                  op: tag
                  days: 1
    """
