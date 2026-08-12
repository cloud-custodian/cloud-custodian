# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import CrossAccountAccessFilter
from c7n.filters.policystatement import HasStatementFilter
from c7n.manager import resources
from c7n.query import (
    ChildDescribeSource,
    ChildResourceManager,
    DescribeSource,
    QueryResourceManager,
    TypeInfo,
)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session


def _augment_tags(manager, resources):
    client = local_session(manager.session_factory).client('s3tables')
    arn_key = manager.resource_type.arn
    for r in resources:
        tags = manager.retry(
            client.list_tags_for_resource, resourceArn=r[arn_key]).get('tags', {})
        r['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]
    return resources


class DescribeTableBucket(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        return _augment_tags(self.manager, resources)


@resources.register('s3-table-bucket')
class TableBucket(QueryResourceManager):
    """AWS S3 Tables - Table Bucket

    https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html
    """

    class resource_type(TypeInfo):
        service = 's3tables'
        enum_spec = ('list_table_buckets', 'tableBuckets', None)
        arn = id = 'arn'
        name = 'name'
        date = 'createdAt'
        cfn_type = 'AWS::S3Tables::TableBucket'
        permission_prefix = 's3tables'
        permissions_augment = ('s3tables:ListTagsForResource',)

    source_mapping = {'describe': DescribeTableBucket}


class DescribeTable(ChildDescribeSource):

    def augment(self, resources):
        return _augment_tags(self.manager, resources)


@resources.register('s3-table')
class Table(ChildResourceManager):
    """AWS S3 Tables - Table

    https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html
    """

    class resource_type(TypeInfo):
        service = 's3tables'
        parent_spec = ('s3-table-bucket', 'tableBucketARN', True)
        enum_spec = ('list_tables', 'tables', None)
        arn = id = 'tableARN'
        name = 'name'
        date = 'createdAt'
        cfn_type = 'AWS::S3Tables::Table'
        permission_prefix = 's3tables'
        permissions_augment = ('s3tables:ListTagsForResource',)

    source_mapping = {'describe-child': DescribeTable}


def _table_namespace(resource):
    ns = resource['namespace']
    return ns[0] if isinstance(ns, list) else ns


class TableBucketPolicyMixin:
    """Annotates table buckets with their resource policy under c7n:Policy."""

    policy_attribute = 'c7n:Policy'

    def policy_annotate(self, client, resource):
        if self.policy_attribute in resource:
            return resource
        try:
            resp = client.get_table_bucket_policy(tableBucketARN=resource['arn'])
            resource[self.policy_attribute] = resp.get('resourcePolicy')
        except client.exceptions.NotFoundException:
            resource[self.policy_attribute] = None
        return resource


class TablePolicyMixin:
    """Annotates tables with their resource policy under c7n:Policy."""

    policy_attribute = 'c7n:Policy'

    def policy_annotate(self, client, resource):
        if self.policy_attribute in resource:
            return resource
        try:
            resp = client.get_table_policy(
                tableBucketARN=resource['c7n:parent-id'],
                namespace=_table_namespace(resource),
                name=resource['name'])
            resource[self.policy_attribute] = resp.get('resourcePolicy')
        except client.exceptions.NotFoundException:
            resource[self.policy_attribute] = None
        return resource


@TableBucket.filter_registry.register('cross-account')
class TableBucketCrossAccount(TableBucketPolicyMixin, CrossAccountAccessFilter):
    """Filter table buckets whose resource policy grants access
    outside of allowed accounts or organizations.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-bucket-cross-account
            resource: aws.s3-table-bucket
            filters:
              - type: cross-account
                whitelist_orgids:
                  - o-xxxxxxxxxx
    """
    permissions = ('s3tables:GetTableBucketPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3tables')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)


@Table.filter_registry.register('cross-account')
class TableCrossAccount(TablePolicyMixin, CrossAccountAccessFilter):
    """Filter tables whose resource policy grants access
    outside of allowed accounts or organizations.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-cross-account
            resource: aws.s3-table
            filters:
              - type: cross-account
                whitelist_orgids:
                  - o-xxxxxxxxxx
    """
    permissions = ('s3tables:GetTablePolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3tables')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)


@TableBucket.filter_registry.register('has-statement')
class TableBucketHasStatement(TableBucketPolicyMixin, HasStatementFilter):
    """Find table buckets with matching resource policy statements.

    Table buckets without an attached policy have an empty ``c7n:Policy``
    annotation, so a policy-required control can be expressed by asserting
    a mandatory statement is present.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-bucket-require-ssl-statement
            resource: aws.s3-table-bucket
            filters:
              - type: has-statement
                statements:
                  - Effect: Deny
                    Condition:
                        Bool:
                            "aws:SecureTransport": "false"
    """
    permissions = ('s3tables:GetTableBucketPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3tables')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)

    def get_std_format_args(self, bucket):
        return {
            'table_bucket_arn': bucket['arn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }


@Table.filter_registry.register('has-statement')
class TableHasStatement(TablePolicyMixin, HasStatementFilter):
    """Find tables with matching resource policy statements.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-require-ssl-statement
            resource: aws.s3-table
            filters:
              - type: has-statement
                statements:
                  - Effect: Deny
                    Condition:
                        Bool:
                            "aws:SecureTransport": "false"
    """
    permissions = ('s3tables:GetTablePolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('s3tables')
        resources = [self.policy_annotate(client, r) for r in resources]
        return super().process(resources, event)

    def get_std_format_args(self, table):
        return {
            'table_arn': table['tableARN'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }


@TableBucket.action_registry.register('tag')
@Table.action_registry.register('tag')
class TagS3TablesResource(Tag):
    """Create tags on an S3 Tables table bucket or table.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-bucket-tag
            resource: aws.s3-table-bucket
            actions:
              - type: tag
                key: owner
                value: data-platform
    """
    permissions = ('s3tables:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {t['Key']: t['Value'] for t in new_tags}
        arn_key = self.manager.resource_type.arn
        for r in resources:
            try:
                client.tag_resource(resourceArn=r[arn_key], tags=tags)
            except client.exceptions.NotFoundException:
                continue


@TableBucket.action_registry.register('remove-tag')
@Table.action_registry.register('remove-tag')
class RemoveTagS3TablesResource(RemoveTag):
    """Remove tags from an S3 Tables table bucket or table.

    :example:

    .. code-block:: yaml

        policies:
          - name: s3-table-bucket-remove-tag
            resource: aws.s3-table-bucket
            actions:
              - type: remove-tag
                tags: ["expired-tag"]
    """
    permissions = ('s3tables:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        arn_key = self.manager.resource_type.arn
        for r in resources:
            try:
                client.untag_resource(resourceArn=r[arn_key], tagKeys=tags)
            except client.exceptions.NotFoundException:
                continue


TableBucket.filter_registry.register('marked-for-op', TagActionFilter)
TableBucket.action_registry.register('mark-for-op', TagDelayedAction)
Table.filter_registry.register('marked-for-op', TagActionFilter)
Table.action_registry.register('mark-for-op', TagDelayedAction)
