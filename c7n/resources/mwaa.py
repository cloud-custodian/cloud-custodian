# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.filters.kms import KmsRelatedFilter
from c7n.tags import RemoveTag, Tag, TagDelayedAction, TagActionFilter

@resources.register('mwaa')
class ApacheAirflow(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'mwaa'
        id = name = 'Name'
        enum_spec = ('list_environments', 'Environments', None)
        detail_spec = ('get_environment', 'Name', None, 'Environment')
        arn = 'Arn'
        arn_type = 'environment'
        cfn_type = 'AWS::MWAA::Environment'
    
    permissions = (
        'environment:GetEnvironment',
        'environment:ListEnvironments',
    )

    def augment(self, resources):
        resources = super(ApacheAirflow, self).augment(resources)
        for r in resources:
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.get('Tags', {}).items()]
        return resources

@ApacheAirflow.filter_registry.register('kms-key')
class ApacheAirflowKmsFilter(KmsRelatedFilter):
    """

    Filter a Managed Workflow for Apache Airflow environment by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: mwaa-kms-key-filter
            resource: mwaa
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/mwaa
    """
    RelatedIdsExpression = 'KmsKey'

@ApacheAirflow.action_registry.register('tag')
class TagApacheAirflow(Tag):
    """Action to create tag(s) on a Managed Workflow for Apache Airflow environment

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-mwaa
                resource: mwaa
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('environment:TagResource',)

    def process_resource_set(self, client, mwaa, new_tags):
        for r in mwaa:
            try:
                client.tag_resource(
                    ResourceArn=r['Arn'],
                    Tags={t['Key']: t['Value'] for t in new_tags})
            except client.exceptions.ResourceNotFound:
                continue


@ApacheAirflow.action_registry.register('remove-tag')
class UntagApacheAirflow(RemoveTag):
    """Action to remove tag(s) on a Managed Workflow for Apache Airflow environment

    :example:

    .. code-block:: yaml

            policies:
              - name: mwaa-remove-tag
                resource: mmwaa
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    permissions = ('environment:UntagResource',)

    def process_resource_set(self, client, mq, tags):
        for r in mq:
            try:
                client.untag_resource(ResourceArn=r['Arn'], tagKeys=tags)
            except client.exceptions.ResourceNotFound:
                continue


ApacheAirflow.filter_registry.register('marked-for-op', TagActionFilter)
ApacheAirflow.action_registry.register('mark-for-op', TagDelayedAction)