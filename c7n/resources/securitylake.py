# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session, type_schema, get_retry


securitylake_retry = get_retry(
    ('ThrottlingException', 'InternalServerException', 'ConflictException'))


class SecurityLakeDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        client = local_session(self.manager.session_factory).client('securitylake')
        arn_key = self.manager.resource_type.arn
        for r in resources:
            tags = self.manager.retry(
                client.list_tags_for_resource,
                resourceArn=r[arn_key]).get('tags', [])
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in tags]
        return resources


@resources.register('security-lake')
class SecurityLakeDataLake(QueryResourceManager):
    """AWS Security Lake data lake.

    :example:

    .. code-block:: yaml

        policies:
          - name: security-lake-minimum-lifecycle
            resource: aws.security-lake
            filter:
            - type: value
              key: lifecycleConfiguration.expiration.days
              op: lt
              value: 7
    """

    class resource_type(TypeInfo):
        service = 'securitylake'
        enum_spec = ('list_data_lakes', 'dataLakes', None)
        arn = id = 'dataLakeArn'
        name = 'region'
        arn_type = 'data-lake'
        permission_prefix = 'securitylake'
        permissions_augment = ('securitylake:ListTagsForResource',)

    source_mapping = {'describe': SecurityLakeDescribe}
    retry = staticmethod(securitylake_retry)


@resources.register('security-lake-subscriber')
class SecurityLakeSubscriber(QueryResourceManager):
    """AWS Security Lake subscriber.

    :example:

    .. code-block:: yaml

        policies:
          - name: security-lake-access-type
            resource: aws.security-lake-subscriber
            filters:
            - type: value
              key: accessTypes
              op: contains
              value: LAKEFORMATION
    """

    class resource_type(TypeInfo):
        service = 'securitylake'
        enum_spec = ('list_subscribers', 'subscribers', None)
        arn = 'subscriberArn'
        id = 'subscriberId'
        name = 'subscriberName'
        date = 'createdAt'
        arn_type = 'subscriber'
        permission_prefix = 'securitylake'
        permissions_augment = ('securitylake:ListTagsForResource',)

    source_mapping = {'describe': SecurityLakeDescribe}
    retry = staticmethod(securitylake_retry)


@SecurityLakeDataLake.action_registry.register('tag')
@SecurityLakeSubscriber.action_registry.register('tag')
class TagSecurityLakeResource(Tag):
    """Add tag(s) to a Security Lake resource.

    :example:

    .. code-block:: yaml

        policies:
          - name: tag-security-lake-subscriber
            resource: aws.security-lake-subscriber
            actions:
              - type: tag
                key: owner
                value: security
    """

    permissions = ('securitylake:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = [{'key': t['Key'], 'value': t['Value']} for t in new_tags]
        arn_key = self.manager.resource_type.arn
        for r in resources:
            client.tag_resource(resourceArn=r[arn_key], tags=tags)


@SecurityLakeDataLake.action_registry.register('remove-tag')
@SecurityLakeSubscriber.action_registry.register('remove-tag')
class RemoveTagSecurityLakeResource(RemoveTag):
    """Remove tag(s) from a Security Lake resource.

    :example:

    .. code-block:: yaml

        policies:
          - name: untag-security-lake-subscriber
            resource: aws.security-lake-subscriber
            actions:
              - type: remove-tag
                tags: ['owner']
    """

    permissions = ('securitylake:UntagResource',)

    def process_resource_set(self, client, resources, tag_keys):
        arn_key = self.manager.resource_type.arn
        for r in resources:
            client.untag_resource(resourceArn=r[arn_key], tagKeys=tag_keys)


for klass in (SecurityLakeDataLake, SecurityLakeSubscriber):
    klass.action_registry.register('mark-for-op', TagDelayedAction)
    klass.filter_registry.register('marked-for-op', TagActionFilter)


@SecurityLakeDataLake.action_registry.register('delete')
class DeleteSecurityLakeDataLake(BaseAction):
    """Delete a Security Lake data lake in its region.

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-security-lake
            resource: aws.security-lake
            actions:
              - delete
    """

    permissions = ('securitylake:DeleteDataLake',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('securitylake')
        for r in resources:
            self.manager.retry(
                client.delete_data_lake,
                regions=[r['region']],
                ignore_err_codes=('ResourceNotFoundException',))


@SecurityLakeSubscriber.action_registry.register('delete')
class DeleteSecurityLakeSubscriber(BaseAction):
    """Delete a Security Lake subscriber.

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-security-lake-subscriber
            resource: aws.security-lake-subscriber
            filters:
              - type: marked-for-op
                op: delete
            actions:
              - delete
    """

    permissions = ('securitylake:DeleteSubscriber',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('securitylake')
        for r in resources:
            self.manager.retry(
                client.delete_subscriber,
                subscriberId=r['subscriberId'],
                ignore_err_codes=('ResourceNotFoundException',))
