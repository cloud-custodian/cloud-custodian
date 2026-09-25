# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeWithResourceTags
from c7n.tags import Tag, RemoveTag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema, get_retry
from c7n.actions import BaseAction


@resources.register('aiops-investigation-group')
class AIOpsInvestigationGroup(QueryResourceManager):
    """AWS AIOps Investigation Group

    :example:

    Find investigation groups not using a customer managed KMS key:

    .. code-block:: yaml

        policies:
          - name: aiops-investigation-group-no-cmk
            resource: aws.aiops-investigation-group
            filters:
              - type: value
                key: encryptionConfiguration.type
                value: AWS_OWNED_KEY
    """

    class resource_type(TypeInfo):
        service = 'aiops'
        enum_spec = ('list_investigation_groups', 'investigationGroups', None)
        detail_spec = ('get_investigation_group', 'identifier', 'arn', None)
        id = arn = 'arn'
        name = 'name'
        date = 'lastModifiedAt'
        permissions_augment = ('aiops:ListTagsForResource',)

    retry = staticmethod(get_retry((
        'ThrottlingException',
        'ConflictException',
        'InternalServerException',
    )))

    source_mapping = {'describe': DescribeWithResourceTags}


@AIOpsInvestigationGroup.action_registry.register('tag')
class TagInvestigationGroup(Tag):
    """Add tags to an investigation group.

    :example:

    .. code-block:: yaml

        policies:
          - name: aiops-investigation-group-tag
            resource: aws.aiops-investigation-group
            actions:
              - type: tag
                key: Env
                value: production
    """

    permissions = ('aiops:TagResource',)

    def process_resource_set(self, client, resource_set, tags):
        new_tags = {t['Key']: t['Value'] for t in tags}
        for r in resource_set:
            self.manager.retry(
                client.tag_resource, resourceArn=r['arn'], tags=new_tags)


@AIOpsInvestigationGroup.action_registry.register('remove-tag')
class RemoveTagInvestigationGroup(RemoveTag):
    """Remove tags from an investigation group.

    :example:

    .. code-block:: yaml

        policies:
          - name: aiops-investigation-group-remove-tag
            resource: aws.aiops-investigation-group
            actions:
              - type: remove-tag
                tags:
                  - Env
    """

    permissions = ('aiops:UntagResource',)

    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            self.manager.retry(
                client.untag_resource, resourceArn=r['arn'], tagKeys=tag_keys)


AIOpsInvestigationGroup.filter_registry.register('marked-for-op', TagActionFilter)
AIOpsInvestigationGroup.action_registry.register('mark-for-op', TagDelayedAction)


@AIOpsInvestigationGroup.action_registry.register('delete')
class DeleteInvestigationGroup(BaseAction):
    """Delete an investigation group.

    :example:

    .. code-block:: yaml

        policies:
          - name: aiops-delete-untagged-investigation-groups
            resource: aws.aiops-investigation-group
            filters:
              - 'tag:Owner': absent
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    permissions = ('aiops:DeleteInvestigationGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('aiops')
        for r in resources:
            self.manager.retry(
                client.delete_investigation_group,
                identifier=r['arn'],
                ignore_err_codes=('ResourceNotFoundException',),
            )
