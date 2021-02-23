# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema


@resources.register('app-flow')
class AppFlow(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'appflow'
        arn_type = 'flow'
        enum_spec = ('list_flows', 'flows', {'maxResults': 100})
        id = name = 'flowName'
        arn = 'flowArn'
        detail_spec = ('describe_flow', 'flowName', 'flowName', None)

    def augment(self, resources):
        resources = super(AppFlow, self).augment(resources)
        for r in resources:
            if 'tags' in r:
                r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['tags'].items()]
        return resources


@AppFlow.action_registry.register('tag')
class TagAppFlowResource(Tag):
    """Action to create tag(s) on an AppFlow resource

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-app-flow
              resource: app-flow
              actions:
                - type: tag
                  key: tag-key
                  value: tag-value
    """

    permissions = ('appflow:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {t.get('Key'): t.get('Value') for t in new_tags}
        for r in resources:
            client.tag_resource(resourceArn=r['flowArn'], tags=tags)


@AppFlow.action_registry.register('remove-tag')
class RemoveTagAppFlowResource(RemoveTag):
    """Action to remove tag(s) on an AppFlow resource

    :example:

    .. code-block:: yaml

        policies:
            - name: untag-app-flow
              resource: app-flow
              actions:
                - type: remove-tag
                  tags: ['tag-key']
    """

    permissions = ('appflow:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            client.untag_resource(resourceArn=r['flowArn'], tagKeys=tag_keys)


AppFlow.action_registry.register('mark-for-op', TagDelayedAction)
AppFlow.filter_registry.register('marked-for-op', TagActionFilter)


@AppFlow.action_registry.register('delete')
class DeleteAppFlowResource(BaseAction):
    """Action to delete an AppFlow

    The 'force' parameter is needed when deleting an AppFlow that is currently
    in use.

    :example:

    .. code-block:: yaml

            policies:
              - name: app-flow-delete
                resource: app-flow
                filters:
                  - type: marked-for-op
                    op: delete
                actions:
                  - type: delete
                    force: true
    """

    permissions = ('appflow:DeleteFlow',)
    schema = type_schema('delete', force={'type': 'boolean'})

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('appflow')
        force_delete = self.data.get('force', False)
        for r in resources:
            self.manager.retry(
                client.delete_flow,
                flowName=r['flowName'],
                forceDelete=force_delete,
                ignore_err_codes=('ResourceNotFoundException',)
            )
