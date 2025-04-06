# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema
from c7n.filters import ValueFilter
from botocore.exceptions import ClientError
from concurrent.futures import as_completed


class AppFlowDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            if 'tags' in r:
                r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['tags'].items()]
        return resources


@resources.register('app-flow')
class AppFlow(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'appflow'
        arn_type = 'flow'
        enum_spec = ('list_flows', 'flows', {'maxResults': 100})
        id = name = 'flowName'
        arn = 'flowArn'
        detail_spec = ('describe_flow', 'flowName', 'flowName', None)
        config_type = "AWS::AppFlow::Flow"

    source_mapping = {'describe': AppFlowDescribe, 'config': ConfigSource}


@AppFlow.filter_registry.register('kms-key')
class AppFlowKmsKeyFilter(ValueFilter):
    """
    Filters app flow items based on their kms-key data

    :example:

    .. code-block:: yaml

      policies:
        - name: app-flow
          resource: app-flow
          filters:
            - type: kms-key
              key: KeyManager
              value: AWS
    """

    schema = type_schema(
        'kms-key',
        rinherit=ValueFilter.schema
    )
    permissions = ('kms:DescribeKey',)
    annotate = True
    annotation_key = 'c7n:KmsKey'

    @staticmethod
    def _describe_key(arn, client):
        try:
            return client.describe_key(KeyId=arn)['KeyMetadata']
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NotFoundException':
                return {}
            raise

    def process(self, resources, event=None):
        keys = {}
        for res in resources:
            if self.annotation_key in res:
                continue
            arn = res.get('kmsArn')
            if arn:
                keys.setdefault(arn, []).append(res)
        if not keys:
            return super().process(resources, event)  # pragma: no cover

        client = local_session(self.manager.session_factory).client('kms')
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for arn in keys:
                futures[w.submit(self._describe_key, arn, client)] = arn
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception getting kms key for app-flow \n %s" % (
                            f.exception()))
                    continue
                data = f.result()
                for res in keys[futures[f]]:
                    res[self.annotation_key] = data
        return super().process(resources, event)

    def __call__(self, r):
        if self.annotate:
            item = r.setdefault(self.annotation_key, {})
        else:
            item = r.pop(self.annotation_key, {})  # pragma: no cover
        return super().__call__(item)


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
