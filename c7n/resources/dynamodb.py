# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import BaseAction, ModifyVpcSecurityGroupsAction
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n import query
from c7n.manager import resources
from c7n.tags import (
    TagDelayedAction, RemoveTag, TagActionFilter, Tag, universal_augment)
from c7n.utils import (
    local_session, chunks, type_schema, snapshot_identifier)
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from datetime import datetime, timedelta
from c7n.filters import Filter
from c7n.filters import ValueFilter
from c7n.query import RetryPageIterator
from c7n.filters.backup import ConsecutiveAwsBackupsFilter
from c7n.filters.policystatement import HasStatementFilter


class ConfigTable(query.ConfigSource):

    def load_resource(self, item):
        resource = super(ConfigTable, self).load_resource(item)
        sse_info = resource.pop('Ssedescription', None)
        if sse_info is None:
            return resource
        resource['SSEDescription'] = sse_info
        for k, r in (('KmsmasterKeyArn', 'KMSMasterKeyArn'),
                     ('Ssetype', 'SSEType')):
            if k in sse_info:
                sse_info[r] = sse_info.pop(k)
        return resource


class DescribeTable(query.DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager,
            super(DescribeTable, self).augment(resources))


@resources.register('dynamodb-table')
class Table(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'dynamodb'
        arn_type = 'table'
        enum_spec = ('list_tables', 'TableNames', None)
        detail_spec = ("describe_table", "TableName", None, "Table")
        id = 'TableName'
        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'
        cfn_type = config_type = 'AWS::DynamoDB::Table'
        universal_taggable = object()
        arn = 'TableArn'
        permissions_augment = ("dynamodb:ListTagsOfResource",)

    source_mapping = {
        'describe': DescribeTable,
        'config': ConfigTable
    }


@Table.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'SSEDescription.KMSMasterKeyArn'


@Table.filter_registry.register('continuous-backup')
class TableContinuousBackupFilter(ValueFilter):
    """Check for continuous backups and point in time recovery (PITR) on a dynamodb table.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-continuous-backups-disabled
                resource: aws.dynamodb-table
                filters:
                  - type: continuous-backup
                    key: ContinuousBackupsStatus
                    op: eq
                    value: DISABLED
              - name: dynamodb-pitr-disabled
                resource: aws.dynamodb-table
                filters:
                  - type: continuous-backup
                    key: PointInTimeRecoveryDescription.PointInTimeRecoveryStatus
                    op: ne
                    value: ENABLED
    """

    annotation_key = 'c7n:continuous-backup'
    annotate = False
    schema = type_schema('continuous-backup', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('dynamodb:DescribeContinuousBackups',)

    def process(self, resources, event=None):
        self.augment([r for r in resources if self.annotation_key not in r])
        return super().process(resources, event)

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for r in resources:
            try:
                r[self.annotation_key] = client.describe_continuous_backups(
                    TableName=r['TableName']).get('ContinuousBackupsDescription', {})
            except client.exceptions.TableNotFoundException:
                continue

    def __call__(self, r):
        return super().__call__(r.get(self.annotation_key, {}))


@Table.filter_registry.register('cross-account')
class CrossAccountTable(CrossAccountAccessFilter):

    permissions = ('dynamodb:GetResourcePolicy',)
    policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for r in resources:
            if self.policy_attribute in r:
                continue
            result = self.manager.retry(
                client.get_resource_policy,
                ResourceArn=r['TableArn'],
                ignore_err_codes=('ResourceNotFoundException', 'PolicyNotFoundException'))
            if result is not None:
                r[self.policy_attribute] = result['Policy']
        return super().process(resources)


@Table.filter_registry.register('has-statement')
class HasStatementTable(HasStatementFilter):

    permissions = ('dynamodb:GetResourcePolicy',)
    policy_attribute = 'c7n:Policy'

    def get_std_format_args(self, table):
        return {
            'table_arn': table[self.manager.resource_type.arn],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for r in resources:
            if self.policy_attribute in r:
                continue
            result = self.manager.retry(
                client.get_resource_policy,
                ResourceArn=r['TableArn'],
                ignore_err_codes=('ResourceNotFoundException', 'PolicyNotFoundException'))
            if result is not None:
                r[self.policy_attribute] = result['Policy']
        return super().process(resources)


@Table.action_registry.register('set-continuous-backup')
class TableContinuousBackupAction(BaseAction):
    """Set continuous backups and point in time recovery (PITR) on a dynamodb table.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-continuous-backups-disabled-set
                resource: aws.dynamodb-table
                filters:
                  - type: continuous-backup
                    key: ContinuousBackupsStatus
                    op: eq
                    value: DISABLED
                actions:
                  - type: set-continuous-backup

    """
    valid_status = ('ACTIVE',)
    schema = type_schema(
        'set-continuous-backup',
        state={'type': 'boolean', 'default': True})
    permissions = ('dynamodb:UpdateContinuousBackups',)

    def process(self, resources):
        resources = self.filter_resources(
            resources, 'TableStatus', self.valid_status)
        if not len(resources):
            return
        client = local_session(self.manager.session_factory).client('dynamodb')
        for r in resources:
            try:
                client.update_continuous_backups(
                    TableName=r['TableName'],
                    PointInTimeRecoverySpecification={
                        'PointInTimeRecoveryEnabled': self.data.get('state', True)
                    })
            except client.exceptions.TableNotFoundException:
                continue


@Table.action_registry.register('update')
class UpdateTable(BaseAction):
    """Modifies the provisioned throughput settings, global secondary indexes,
    or DynamoDB Streams settings for a given table.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-change-billing-mode
                resource: aws.dynamodb-table
                actions:
                  - type: update
                    BillingMode: PAY_PER_REQUEST

    """
    valid_status = ('ACTIVE',)
    schema = type_schema(
        'update',
        BillingMode={'enum': ['PROVISIONED', 'PAY_PER_REQUEST']},
        DeletionProtectionEnabled={'enum': [True, False]},
        ProvisionedThroughput={'type': 'object',
            'properties': {
                'ReadCapacityUnits': {'type': 'integer'},
                'WriteCapacityUnits': {'type': 'integer'}}})
    permissions = ('dynamodb:UpdateTable',)

    def process(self, resources):
        resources = self.filter_resources(
            resources, 'TableStatus', self.valid_status)
        if not resources:
            return
        params = copy.deepcopy(self.data)
        params.pop("type")
        client = local_session(self.manager.session_factory).client('dynamodb')
        for r in resources:
            try:
                client.update_table(TableName=r['TableName'], **params)
            except client.exceptions.TableNotFoundException:
                continue


@Table.action_registry.register('delete')
class DeleteTable(BaseAction):
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
    schema = type_schema('delete',
        force={'type': 'boolean', 'default': False})
    permissions = ("dynamodb:UpdateTable", "dynamodb:DeleteTable",)

    def delete_table(self, client, table_set):
        if self.data.get('force', False):
            del_protection_updater = self.manager.action_registry['update'](
                {'type': 'update', 'DeletionProtectionEnabled': False}, self.manager)
            del_protection_updater.process(table_set)
        for t in table_set:
            client.delete_table(TableName=t['TableName'])

    def process(self, resources):
        resources = self.filter_resources(
            resources, 'TableStatus', self.valid_status)
        if not len(resources):
            return

        futures = []
        client = local_session(self.manager.session_factory).client('dynamodb')

        with self.executor_factory(max_workers=2) as w:
            for table_set in chunks(resources, 20):
                futures.append(w.submit(self.delete_table, client, table_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting dynamodb table set \n %s"
                        % (f.exception()))


@Table.action_registry.register('set-stream')
class SetStream(BaseAction):
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
        tables = self.filter_resources(
            tables, 'TableStatus', self.valid_status)
        if not len(tables):
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
class CreateBackup(BaseAction):
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
        resources = self.filter_resources(
            resources, 'TableStatus', self.valid_status)
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

    class resource_type(query.TypeInfo):
        service = 'dynamodb'
        arn = 'BackupArn'
        enum_spec = ('list_backups', 'BackupSummaries', None)
        id = 'BackupArn'
        name = 'BackupName'
        date = 'BackupCreationDateTime'


@Backup.action_registry.register('delete')
class DeleteBackup(BaseAction):
    """Deletes backups of a DynamoDB table

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-delete-backup
                resource: dynamodb-backup
                filters:
                  - type: value
                    key: BackupCreationDateTime
                    op: greater-than
                    value_type: age
                    value: 28
                actions:
                  - type: delete
    """

    valid_status = ('AVAILABLE',)
    schema = type_schema('delete')
    permissions = ('dynamodb:DeleteBackup',)

    def process(self, backups):
        backups = self.filter_resources(
            backups, 'BackupStatus', self.valid_status)
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
                    self.log.warning("Could not complete DynamoDB backup deletion for table:%s", t)
                    continue
                raise


@resources.register('dynamodb-stream')
class Stream(query.QueryResourceManager):
    # Note stream management takes place on the table resource

    class resource_type(query.TypeInfo):
        service = 'dynamodbstreams'
        permission_prefix = 'dynamodb'
        # Note max rate of 5 calls per second
        enum_spec = ('list_streams', 'Streams', None)
        # Note max rate of 10 calls per second.
        detail_spec = (
            "describe_stream", "StreamArn", "StreamArn", "StreamDescription")
        arn = id = 'StreamArn'
        arn_type = 'stream'

        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'


class DescribeDaxCluster(query.DescribeSource):

    def get_resources(self, ids, cache=True):
        """Retrieve dax resources for serverless policies or related resources
        """
        client = local_session(self.manager.session_factory).client('dax')
        return client.describe_clusters(ClusterNames=ids).get('Clusters')

    def augment(self, clusters):
        resources = super(DescribeDaxCluster, self).augment(clusters)
        return list(filter(None, _dax_cluster_tags(
            resources,
            self.manager.session_factory,
            self.manager.retry,
            self.manager.log)))


@resources.register('dax')
class DynamoDbAccelerator(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'dax'
        arn_type = 'cache'
        enum_spec = ('describe_clusters', 'Clusters', None)
        arn = 'ClusterArn'
        id = name = 'ClusterName'
        cfn_type = 'AWS::DAX::Cluster'

    permissions = ('dax:ListTags',)
    source_mapping = {
        'describe': DescribeDaxCluster,
        'config': query.ConfigSource
    }

    def get_resources(self, ids, cache=True, augment=True):
        """Override in order to disable the augment for serverless policies.
           list_tags on dax resources always fail until the cluster is finished creating.
        """
        return super(DynamoDbAccelerator, self).get_resources(ids, cache, augment=False)


def _dax_cluster_tags(tables, session_factory, retry, log):
    client = local_session(session_factory).client('dax')

    def process_tags(r):
        try:
            r['Tags'] = retry(
                client.list_tags, ResourceName=r['ClusterArn'])['Tags']
            return r
        except (client.exceptions.ClusterNotFoundFault,
                client.exceptions.InvalidClusterStateFault):
            return None

    return filter(None, list(map(process_tags, tables)))


DynamoDbAccelerator.filter_registry.register('marked-for-op', TagActionFilter)


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

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            try:
                client.tag_resource(ResourceName=r['ClusterArn'], Tags=tags)
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.InvalidARNFault,
                    client.exceptions.InvalidClusterStateFault) as e:
                self.log.warning('Exception tagging %s: \n%s', r['ClusterName'], e)


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

    def process_resource_set(self, client, resources, tag_keys):
        for r in resources:
            try:
                client.untag_resource(
                    ResourceName=r['ClusterArn'], TagKeys=tag_keys)
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.TagNotFoundFault,
                    client.exceptions.InvalidClusterStateFault) as e:
                self.log.warning('Exception removing tags on %s: \n%s', r['ClusterName'], e)


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


@DynamoDbAccelerator.action_registry.register('delete')
class DaxDeleteCluster(BaseAction):
    """Action to delete a DAX cluster

    :example:

    .. code-block:: yaml

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
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.InvalidARNFault,
                    client.exceptions.InvalidClusterStateFault) as e:
                self.log.warning('Exception marking %s: \n%s', r['ClusterName'], e)


@DynamoDbAccelerator.action_registry.register('update-cluster')
class DaxUpdateCluster(BaseAction):
    """Updates a DAX cluster configuration

    :example:

    .. code-block:: yaml

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
            except (client.exceptions.ClusterNotFoundFault,
                    client.exceptions.InvalidClusterStateFault) as e:
                self.log.warning(
                    'Exception updating dax cluster %s: \n%s',
                    r['ClusterName'], e)


@DynamoDbAccelerator.action_registry.register('modify-security-groups')
class DaxModifySecurityGroup(ModifyVpcSecurityGroupsAction):

    permissions = ('dax:UpdateCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dax')
        groups = super(DaxModifySecurityGroup, self).get_groups(resources)

        for idx, r in enumerate(resources):
            client.update_cluster(
                ClusterName=r['ClusterName'], SecurityGroupIds=groups[idx])


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


@Table.filter_registry.register('consecutive-backups')
class TableConsecutiveBackups(Filter):
    """Returns tables where number of consective daily backups is
    equal to/or greater than n days.

    :example:

    .. code-block:: yaml

            policies:
              - name: dynamodb-daily-backup-count
                resource: dynamodb-table
                filters:
                  - type: consecutive-backups
                    count: 7
                    period: days
                    backuptype: SYSTEM
                    status: AVAILABLE
    """
    schema = type_schema('consecutive-backups', count={'type': 'number', 'minimum': 1},
        period={'enum': ['hours', 'days', 'weeks']},
        backuptype={'enum': ['SYSTEM', 'USER', 'AWS_BACKUP', 'ALL']},
        status={'enum': ['AVAILABLE', 'CREATING', 'DELETED']},
        required=['count', 'period', 'status', 'backuptype'])
    permissions = ('dynamodb:ListBackups', 'dynamodb:DescribeBackup', 'dynamodb:DescribeTable', )
    annotation = 'c7n:DynamodbBackups'

    def process_resource_set(self, client, resources, lbdate):
        paginator = client.get_paginator('list_backups')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        ddb_backups = paginator.paginate(BackupType=self.data.get('backuptype'),
            TimeRangeLowerBound=lbdate).build_full_result().get('BackupSummaries', [])

        table_map = {}
        for backup in ddb_backups:
            table_map.setdefault(backup['TableName'], []).append(backup)
        for r in resources:
            r[self.annotation] = table_map.get(r['TableName'], [])

    def get_date(self, time):
        period = self.data.get('period')
        if period == 'weeks':
            date = (datetime.utcnow() - timedelta(weeks=time)).strftime('%Y-%m-%d')
        elif period == 'hours':
            date = (datetime.utcnow() - timedelta(hours=time)).strftime('%Y-%m-%d-%H')
        else:
            date = (datetime.utcnow() - timedelta(days=time)).strftime('%Y-%m-%d')
        return date

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('dynamodb')
        results = []
        retention = self.data.get('count')
        lbdate = self.get_date(retention)
        expected_dates = set()
        for time in range(1, retention + 1):
            expected_dates.add(self.get_date(time))

        for resource_set in chunks(
                [r for r in resources if self.annotation not in r], 50):
            self.process_resource_set(client, resource_set, lbdate)

        for r in resources:
            backup_dates = set()
            for backup in r[self.annotation]:
                if backup['BackupStatus'] == self.data.get('status'):
                    if self.data.get('period') == 'hours':
                        backup_dates.add(backup['BackupCreationDateTime'].strftime('%Y-%m-%d-%H'))
                    else:
                        backup_dates.add(backup['BackupCreationDateTime'].strftime('%Y-%m-%d'))
            if expected_dates.issubset(backup_dates):
                results.append(r)
        return results


Table.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)
