# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import BaseAction, ModifyVpcSecurityGroupsAction
from c7n.filters import FilterRegistry
from c7n import query
from c7n.manager import resources
from c7n.tags import TagDelayedAction, RemoveTag, TagActionFilter, Tag
from c7n.utils import (
    local_session, get_retry, chunks, type_schema, snapshot_identifier)
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter


filters = FilterRegistry('dynamodb-table.filters')
filters.register('marked-for-op', TagActionFilter)


@resources.register('dynamodb-table')
class Table(query.QueryResourceManager):

    class resource_type(object):
        service = 'dynamodb'
        type = 'table'
        enum_spec = ('list_tables', 'TableNames', None)
        detail_spec = ("describe_table", "TableName", None, "Table")
        id = 'TableName'
        filter_name = None
        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'
        config_type = 'AWS::DynamoDB::Table'

    filter_registry = filters
    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('dynamodb:ListTagsOfResource')

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeTable(self)
        elif source_type == 'config':
            return query.ConfigSource(self)
        raise ValueError('invalid source %s' % source_type)


class DescribeTable(query.DescribeSource):

    def augment(self, tables):
        resources = super(DescribeTable, self).augment(tables)
        return list(filter(None, _dynamodb_table_tags(
            self.manager.get_model(),
            resources,
            self.manager.session_factory,
            self.manager.executor_factory,
            self.manager.retry,
            self.manager.log)))


def _dynamodb_table_tags(
        model, tables, session_factory, executor_factory, retry, log):
    """ Augment DynamoDB tables with their respective tags
    """

    def process_tags(table):
        client = local_session(session_factory).client('dynamodb')
        arn = table['TableArn']
        try:
            tag_list = retry(
                client.list_tags_of_resource,
                ResourceArn=arn)['Tags']
        except ClientError as e:
            log.warning("Exception getting DynamoDB tags  \n %s", e)
            return None
        table['Tags'] = tag_list or []
        return table

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, tables))


class StatusFilter(object):
    """Filter tables by status"""

    valid_states = ()

    def filter_table_state(self, tables, states=None):
        states = states or self.valid_states
        orig_count = len(tables)
        result = [t for t in tables if t['TableStatus'] in states]
        self.log.info("%s %d of %d tables" % (
            self.__class__.__name__, len(result), orig_count))
        return result

    def filter_backup_state(self, tables, states=None):
        states = states or self.valid_states
        orig_count = len(tables)
        result = [t for t in tables if t['BackupStatus'] in states]
        self.log.info("%s %d of %d tables" % (
            self.__class__.__name__, len(result), orig_count))
        return result


@Table.action_registry.register('mark-for-op')
class TagDelayedAction(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamo-mark-tag-compliance
                resource: dynamodb-table
                filters:
                  - "tag:custodian_cleanup": absent
                  - "tag:OwnerName": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Cluster does not have valid OwnerName tag: {op}@{action_date}"
                    op: delete
                    days: 7
    """
    permission = ('dynamodb:TagResource',)
    batch_size = 1

    def process_resource_set(self, tables, tags):
        client = local_session(self.manager.session_factory).client(
            'dynamodb')
        for t in tables:
            arn = t['TableArn']
            client.tag_resource(ResourceArn=arn, Tags=tags)


@Table.action_registry.register('tag')
class TagTable(Tag):
    """Action to create tag(s) on a resource

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-tag-table
                resource: dynamodb-table
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('dynamodb:TagResource',)
    batch_size = 1

    def process_resource_set(self, tables, tags):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for t in tables:
            arn = t['TableArn']
            client.tag_resource(ResourceArn=arn, Tags=tags)


@Table.action_registry.register('remove-tag')
class UntagTable(RemoveTag):
    """Action to remove tag(s) on a resource

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-remove-tag
                resource: dynamodb-table
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('dynamodb:UntagResource',)

    def process_resource_set(self, tables, tag_keys):
        client = local_session(
            self.manager.session_factory).client('dynamodb')
        for t in tables:
            arn = t['TableArn']
            client.untag_resource(
                ResourceArn=arn, TagKeys=tag_keys)


@Table.action_registry.register('delete')
class DeleteTable(BaseAction, StatusFilter):
    """Action to delete dynamodb tables

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-empty-tables
                resource: dynamodb-table
                filters:
                  - TableSizeBytes: 0
                actions:
                  - delete
    """

    valid_status = ('ACTIVE',)
    schema = type_schema('delete')
    permissions = ("dynamodb:DeleteTable",)

    def delete_table(self, table_set):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for t in table_set:
            client.delete_table(TableName=t['TableName'])

    def process(self, resources):
        resources = self.filter_table_state(
            resources, self.valid_status)
        if not len(resources):
            return

        futures = []

        with self.executor_factory(max_workers=2) as w:
            for table_set in chunks(resources, 20):
                futures.append(w.submit(self.delete_table, table_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting dynamodb table set \n %s"
                        % (f.exception()))


@Table.action_registry.register('set-stream')
class SetStream(BaseAction, StatusFilter):
    """Action to enable/disable streams on table.

    :example:

    .. code-block:: yaml

            policies:
              - name: stream-update
                resource: dynamodb-table
                filters:
                  - TableName: 'test'
                  - TableStatus: 'ACTIVE'
                actions:
                  - type: set-stream
                    state: True
                    stream_view_type: 'NEW_IMAGE'

    """

    valid_status = ('ACTIVE',)
    schema = type_schema('set-stream',
                         state={'type': 'boolean'},
                         stream_view_type={'type': 'string'})
    permissions = ("dynamodb:UpdateTable",)

    def process(self, tables):
        tables = self.filter_table_state(
            tables, self.valid_status)
        if not len(tables):
            self.log.warning("Table not in ACTIVE state.")
            return

        state = self.data.get('state')
        type = self.data.get('stream_view_type')

        stream_spec = {"StreamEnabled": state}

        if self.data.get('stream_view_type') is not None:
            stream_spec.update({"StreamViewType": type})

        c = local_session(self.manager.session_factory).client('dynamodb')

        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(c.update_table,
                                TableName=t['TableName'],
                                StreamSpecification=stream_spec): t for t in tables}

        for f in as_completed(futures):
            t = futures[f]
            if f.exception():
                self.log.error(
                    "Exception updating dynamodb table set \n %s"
                    % (f.exception()))
                continue

            if self.data.get('stream_view_type') is not None:
                stream_state = \
                    f.result()['TableDescription']['StreamSpecification']['StreamEnabled']
                stream_type = \
                    f.result()['TableDescription']['StreamSpecification']['StreamViewType']

                t['c7n:StreamState'] = stream_state
                t['c7n:StreamType'] = stream_type


@Table.action_registry.register('backup')
class CreateBackup(BaseAction, StatusFilter):
    """Creates a manual backup of a DynamoDB table. Use of the optional
       prefix flag will attach a user specified prefix. Otherwise,
       the backup prefix will default to 'Backup'.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-create-backup
                resource: dynamodb-table
                actions:
                  - type: backup
                    prefix: custom
    """

    valid_status = ('ACTIVE',)
    schema = type_schema('backup',
                         prefix={'type': 'string'})
    permissions = ('dynamodb:CreateBackup',)

    def process(self, resources):
        resources = self.filter_table_state(
            resources, self.valid_status)
        if not len(resources):
            return

        c = local_session(self.manager.session_factory).client('dynamodb')
        futures = {}

        prefix = self.data.get('prefix', 'Backup')

        with self.executor_factory(max_workers=2) as w:
            for t in resources:
                futures[w.submit(
                    c.create_backup,
                    BackupName=snapshot_identifier(
                        prefix, t['TableName']),
                    TableName=t['TableName'])] = t
            for f in as_completed(futures):
                t = futures[f]
                if f.exception():
                    self.manager.log.warning(
                        "Could not complete DynamoDB backup table:%s", t)
                arn = f.result()['BackupDetails']['BackupArn']
                t['c7n:BackupArn'] = arn


@resources.register('dynamodb-backup')
class Backup(query.QueryResourceManager):
    class resource_type(object):
        service = 'dynamodb'
        type = 'table'
        enum_spec = ('list_backups', 'BackupSummaries', None)
        detail_spec = None
        id = 'Table'
        filter_name = None
        name = 'TableName'
        date = 'BackupCreationDateTime'
        dimension = 'TableName'
        config_type = 'AWS::DynamoDB::Table'


@Backup.action_registry.register('delete')
class DeleteBackup(BaseAction, StatusFilter):
    """Deletes backups of a DynamoDB table

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-delete-backup
                resource: dynamodb-backup
                filters:
                  - type: age
                    days: 28
                    op: ge
                actions:
                  - type: delete
    """

    valid_status = ('AVAILABLE',)
    schema = type_schema('delete')
    permissions = ('dynamodb:DeleteBackup',)

    def process(self, backups):
        backups = self.filter_backup_state(
            backups, self.valid_status)
        if not len(backups):
            return

        c = local_session(self.manager.session_factory).client('dynamodb')

        for table_set in chunks(backups, 20):
            self.process_dynamodb_backups(table_set, c)

    def process_dynamodb_backups(self, table_set, c):

        for t in table_set:
            try:
                c.delete_backup(
                    BackupArn=t['BackupArn'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    self.log.warning("Could not complete DynamoDB backup table:%s", t)
                    continue
                raise


@resources.register('dynamodb-stream')
class Stream(query.QueryResourceManager):
    # Note stream management takes place on the table resource

    class resource_type(object):
        service = 'dynamodbstreams'
        # Note max rate of 5 calls per second
        enum_spec = ('list_streams', 'Streams', None)
        # Note max rate of 10 calls per second.
        detail_spec = (
            "describe_stream", "StreamArn", "StreamArn", "StreamDescription")
        id = 'StreamArn'

        # TODO, we default to filtering by id, but the api takes table names, which
        # require additional client side filtering as multiple streams may be present
        # per table.
        # filter_name = 'TableName'
        filter_name = None

        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'


@resources.register('dax')
class DynamoDbAccelerator(query.QueryResourceManager):

    class resource_type(object):
        service = 'dax'
        type = 'cluster'
        enum_spec = ('describe_clusters', 'Clusters', None)
        detail_spec = None
        id = 'ClusterArn'
        name = 'ClusterName'
        config_type = 'AWS::DAX::Cluster'
        filter_name = None
        dimension = None
        date = None

    retry = staticmethod(get_retry(('Throttled',)))
    filter_registry = FilterRegistry('dynamodb-dax.filters')
    filters.register('marked-for-op', TagActionFilter)
    permissions = ('dax:ListTags',)
    log = logging.getLogger('custodian.dax')

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeDaxCluster(self)
        elif source_type == 'config':
            return query.ConfigSource(self)
        raise ValueError('invalid source %s' % source_type)


class DescribeDaxCluster(query.DescribeSource):

    def augment(self, clusters):
        resources = super(DescribeDaxCluster, self).augment(clusters)
        return list(filter(None, _dax_cluster_tags(
            resources,
            self.manager.session_factory,
            self.manager.executor_factory,
            self.manager.retry,
            self.manager.log)))


def _dax_cluster_tags(tables, session_factory, executor_factory, retry, log):
    client = local_session(session_factory).client('dax')

    def process_tags(r):
        tags = []
        try:
            tags = retry(
                client.list_tags, ResourceName=r['ClusterArn'])['Tags']
        except ClientError as e:
            if e.response['Error']['Code'] in (
                    'ClusterNotFoundFault',
                    'InvalidARNFault',
                    'InvalidClusterStateFault'):
                log.warning('Exception collecting tags for %s: \n%s' % (
                    r['ClusterName'], e))
            else:
                raise
        r['Tags'] = tags
        return r

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, tables))


@DynamoDbAccelerator.filter_registry.register('security-group')
class DaxSecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].SecurityGroupIdentifier"


@DynamoDbAccelerator.action_registry.register('tag')
class DaxTagging(Tag):
    """Action to create tag(s) on a resource

        :example:

        .. code-block:: yaml

            policies:
              - name: dax-cluster-tag
                resource: dax
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """
    permissions = ('dax:TagResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('dax')
        for r in resources:
            try:
                client.tag_resource(ResourceName=r[self.id_key], Tags=tags)
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'ClusterNotFoundFault',
                        'InvalidClusterStateFault',
                        'InvalidARNFault'):
                    self.log.warning('Exception tagging %s: \n%s' % (
                        r['ClusterName'], e))
                    continue
                raise


@DynamoDbAccelerator.action_registry.register('remove-tag')
class DaxRemoveTagging(RemoveTag):
    """Action to remove tag(s) on a resource

    :example:

    .. code-block:: yaml

        policies:
          - name: dax-remove-tag
            resource: dax
            filters:
              - "tag:OutdatedTag": present
            actions:
              - type: remove-tag
                tags: ["OutdatedTag"]
    """
    permissions = ('dax:UntagResource',)

    def process_resource_set(self, resources, tag_keys):
        client = local_session(self.manager.session_factory).client('dax')
        for r in resources:
            try:
                client.untag_resource(
                    ResourceName=r['ClusterArn'], TagKeys=tag_keys)
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'ClusterNotFoundFault',
                        'InvalidARNFault',
                        'InvalidClusterStateFault',
                        'TagNotFoundFault'):
                    self.log.warning('Exception removing tags on %s: \n%s' % (
                        r['ClusterName'], e))
                    continue
                raise


@DynamoDbAccelerator.action_registry.register('mark-for-op')
class DaxMarkForOp(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

        policies:
          - name: dax-mark-tag-compliance
            resource: dax
            filters:
              - "tag:custodian_cleanup": absent
              - "tag:OwnerName": absent
            actions:
              - type: mark-for-op
                tag: custodian_cleanup
                msg: "Missing tag 'OwnerName': {op}@{action_date}"
                op: delete
                days: 7
    """
    permission = ('dax:TagResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('dax')
        for r in resources:
            try:
                client.tag_resource(ResourceName=r[self.id_key], Tags=tags)
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'ClusterNotFoundFault',
                        'InvalidARNFault',
                        'InvalidClusterStateFault'):
                    self.log.warning(
                        'Exception marking %s: \n%s' % (r['ClusterName'], e))
                    continue
                raise


@DynamoDbAccelerator.action_registry.register('delete')
class DaxDeleteCluster(BaseAction):
    """Action to delete a DAX cluster

    :example:

    .. code-block: yaml

        policies:
          - name: dax-delete-cluster
            resource: dax
            filters:
              - "tag:DeleteMe": present
            actions:
              - type: delete
    """
    permissions = ('dax:DeleteCluster',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dax')
        for r in resources:
            try:
                client.delete_cluster(ClusterName=r['ClusterName'])
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'ClusterNotFoundFault',
                        'InvalidClusterStateFault'):
                    self.log.warning('Exception marking %s: \n%s' % (
                        r['ClusterName'], e))
                    continue
                raise


@DynamoDbAccelerator.action_registry.register('update-cluster')
class DaxUpdateCluster(BaseAction):
    """Updates a DAX cluster configuration

    :example:

    .. code-block: yaml

        policies:
          - name: dax-update-cluster
            resource: dax
            filters:
              - ParameterGroup.ParameterGroupName: 'default.dax1.0'
            actions:
              - type: update-cluster
                ParameterGroupName: 'testparamgroup'
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['update-cluster']},
            'Description': {'type': 'string'},
            'PreferredMaintenanceWindow': {'type': 'string'},
            'NotificationTopicArn': {'type': 'string'},
            'NotificationTopicStatus': {'type': 'string'},
            'ParameterGroupName': {'type': 'string'}
        }
    }
    permissions = ('dax:UpdateCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dax')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            params['ClusterName'] = r['ClusterName']
            try:
                client.update_cluster(**params)
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'ClusterNotFoundFault',
                        'InvalidClusterStateFault'):
                    self.log.warning(
                        'Exception updating dax cluster %s: \n%s' % (
                            r['ClusterName'], e))
                    continue
                raise


@DynamoDbAccelerator.action_registry.register('modify-security-groups')
class DaxModifySecurityGroup(ModifyVpcSecurityGroupsAction):

    permissions = ('dax:UpdateCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dax')
        groups = super(DaxModifySecurityGroup, self).get_groups(
            resources, metadata_key='SecurityGroupIdentifier')

        for idx, r in enumerate(resources):
            client.update_cluster(
                ClusterName=r['ClusterName'],
                SecurityGroupIds=groups[idx])


@DynamoDbAccelerator.filter_registry.register('subnet')
class DaxSubnetFilter(SubnetFilter):
    """Filters DAX clusters based on their associated subnet group

    :example:

    .. code-block:: yaml

        policies:
          - name: dax-no-auto-public
            resource: dax
            filters:
              - type: subnet
                key: MapPublicIpOnLaunch
                value: False
    """
    RelatedIdsExpression = ""

    def get_related_ids(self, resources):
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['SubnetGroup']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('dax')
        subnet_groups = client.describe_subnet_groups()['SubnetGroups']
        self.groups = {s['SubnetGroupName']: s for s in subnet_groups}
        return super(DaxSubnetFilter, self).process(resources)
