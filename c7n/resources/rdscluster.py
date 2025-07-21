# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import itertools
from concurrent.futures import as_completed
from datetime import datetime, timedelta
from itertools import chain

from c7n.actions import BaseAction
from c7n.filters import AgeFilter, CrossAccountAccessFilter, Filter, ValueFilter
from c7n.filters.offhours import OffHour, OnHour
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import (
    ConfigSource, QueryResourceManager, TypeInfo, DescribeSource, RetryPageIterator)
from c7n.resources import rds
from c7n.filters.kms import KmsRelatedFilter
from .aws import shape_validate
from c7n.exceptions import PolicyValidationError
from botocore.exceptions import ClientError
from c7n.utils import (
    type_schema, local_session, get_retry, snapshot_identifier, chunks)

from c7n.resources.rds import ParameterFilter
from c7n.filters.backup import ConsecutiveAwsBackupsFilter

log = logging.getLogger('custodian.rds-cluster')


class DescribeCluster(DescribeSource):

    def get_resources(self, ids):
        resources = chain.from_iterable(
            self.query.filter(
                self.manager,
                Filters=[
                    {'Name': 'db-cluster-id', 'Values': ids_chunk}
                ]
            )
            for ids_chunk in chunks(ids, 100)  # DescribeCluster filter length limit
        )
        return list(resources)

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagList', ())
        return resources


class ConfigCluster(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        resource.pop('TagList', None)  # we pull tags from supplementary config
        for k in list(resource.keys()):
            if k.startswith('Dbc'):
                resource["DBC%s" % (k[3:])] = resource.pop(k)
            elif k.startswith('Iamd'):
                resource['IAMD%s' % (k[4:])] = resource.pop(k)
            elif k.startswith('Dbs'):
                resource["DBS%s" % (k[3:])] = resource.pop(k)
        return resource


@resources.register('rds-cluster')
class RDSCluster(QueryResourceManager):
    """Resource manager for RDS clusters.
    """

    class resource_type(TypeInfo):

        service = 'rds'
        arn = 'DBClusterArn'
        arn_type = 'cluster'
        arn_separator = ":"
        enum_spec = ('describe_db_clusters', 'DBClusters', None)
        name = id = 'DBClusterIdentifier'
        config_id = 'DbClusterResourceId'
        dimension = 'DBClusterIdentifier'
        universal_taggable = True
        permissions_enum = ('rds:DescribeDBClusters',)
        cfn_type = config_type = 'AWS::RDS::DBCluster'

    source_mapping = {
        'config': ConfigCluster,
        'describe': DescribeCluster
    }


RDSCluster.filter_registry.register('offhour', OffHour)
RDSCluster.filter_registry.register('onhour', OnHour)


@RDSCluster.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@RDSCluster.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""
    groups = None

    def get_permissions(self):
        return self.manager.get_resource_manager(
            'rds-subnet-group').get_permissions()

    def get_subnet_groups(self):
        return {
            r['DBSubnetGroupName']: r for r in
            self.manager.get_resource_manager('rds-subnet-group').resources()}

    def get_related_ids(self, resources):
        if not self.groups:
            self.groups = self.get_subnet_groups()
        group_ids = set()
        for r in resources:
            group_ids.update(
                [s['SubnetIdentifier'] for s in
                 self.groups[r['DBSubnetGroup']]['Subnets']])
        return group_ids

    def process(self, resources, event=None):
        if not self.groups:
            self.groups = self.get_subnet_groups()
        return super(SubnetFilter, self).process(resources, event)


RDSCluster.filter_registry.register('network-location', net_filters.NetworkLocation)


@RDSCluster.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@RDSCluster.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete a RDS cluster

    To prevent unwanted deletion of clusters, it is recommended to apply a
    filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-delete-unused
                resource: rds-cluster
                filters:
                  - type: metrics
                    name: CPUUtilization
                    days: 21
                    value: 1.0
                    op: le
                actions:
                  - type: delete
                    skip-snapshot: false
                    delete-instances: true
    """

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'},
                     'delete-instances': {'type': 'boolean'}})

    permissions = ('rds:DeleteDBCluster',)

    def process(self, clusters):
        skip = self.data.get('skip-snapshot', False)
        delete_instances = self.data.get('delete-instances', True)
        client = local_session(self.manager.session_factory).client('rds')

        for cluster in clusters:
            if delete_instances:
                for instance in cluster.get('DBClusterMembers', []):
                    client.delete_db_instance(
                        DBInstanceIdentifier=instance['DBInstanceIdentifier'],
                        SkipFinalSnapshot=True)
                    self.log.info(
                        'Deleted RDS instance: %s',
                        instance['DBInstanceIdentifier'])

            params = {'DBClusterIdentifier': cluster['DBClusterIdentifier']}
            if skip:
                params['SkipFinalSnapshot'] = True
            else:
                params['FinalDBSnapshotIdentifier'] = snapshot_identifier(
                    'Final', cluster['DBClusterIdentifier'])

            _run_cluster_method(
                client.delete_db_cluster, params,
                (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
                client.exceptions.InvalidDBClusterStateFault)


@RDSCluster.action_registry.register('retention')
class RetentionWindow(BaseAction):
    """
    Action to set the retention period on rds cluster snapshots,
    enforce (min, max, exact) sets retention days occordingly.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-backup-retention
                resource: rds-cluster
                filters:
                  - type: value
                    key: BackupRetentionPeriod
                    value: 21
                    op: ne
                actions:
                  - type: retention
                    days: 21
                    enforce: min
    """

    date_attribute = "BackupRetentionPeriod"
    # Tag copy not yet available for Aurora:
    #   https://forums.aws.amazon.com/thread.jspa?threadID=225812
    schema = type_schema(
        'retention', **{'days': {'type': 'number'},
                        'enforce': {'type': 'string', 'enum': [
                            'min', 'max', 'exact']}})
    permissions = ('rds:ModifyDBCluster',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('rds')

        for cluster in clusters:
            self.process_snapshot_retention(client, cluster)

    def process_snapshot_retention(self, client, cluster):
        current_retention = int(cluster.get('BackupRetentionPeriod', 0))
        new_retention = self.data['days']
        retention_type = self.data.get('enforce', 'min').lower()
        if retention_type == 'min':
            self.set_retention_window(
                client, cluster, max(current_retention, new_retention))
        elif retention_type == 'max':
            self.set_retention_window(
                client, cluster, min(current_retention, new_retention))
        elif retention_type == 'exact':
            self.set_retention_window(client, cluster, new_retention)

    def set_retention_window(self, client, cluster, retention):
        params = dict(
            DBClusterIdentifier=cluster['DBClusterIdentifier'],
            BackupRetentionPeriod=retention
        )
        if cluster.get('EngineMode') != 'serverless':
            params.update(
                dict(
                    PreferredBackupWindow=cluster['PreferredBackupWindow'],
                    PreferredMaintenanceWindow=cluster['PreferredMaintenanceWindow'])
            )
        _run_cluster_method(
            client.modify_db_cluster,
            params,
            (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
            client.exceptions.InvalidDBClusterStateFault
        )


@RDSCluster.action_registry.register('stop')
class Stop(BaseAction):
    """Stop a running db cluster
    """

    schema = type_schema('stop')
    permissions = ('rds:StopDBCluster',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('rds')
        for c in clusters:
            _run_cluster_method(
                client.stop_db_cluster, dict(DBClusterIdentifier=c['DBClusterIdentifier']),
                (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
                client.exceptions.InvalidDBClusterStateFault)


@RDSCluster.action_registry.register('start')
class Start(BaseAction):
    """Start a stopped db cluster
    """

    schema = type_schema('start')
    permissions = ('rds:StartDBCluster',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('rds')
        for c in clusters:
            _run_cluster_method(
                client.start_db_cluster, dict(DBClusterIdentifier=c['DBClusterIdentifier']),
                (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
                client.exceptions.InvalidDBClusterStateFault)


def _run_cluster_method(method, params, ignore=(), warn=(), method_name=""):
    try:
        method(**params)
    except ignore:
        pass
    except warn as e:
        log.warning(
            "error %s on cluster %s error %s",
            method_name or method.__name__, params['DBClusterIdentifier'], e)


@RDSCluster.action_registry.register('snapshot')
class Snapshot(BaseAction):
    """Action to create a snapshot of a rds cluster

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshot
                resource: rds-cluster
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('rds:CreateDBClusterSnapshot',)

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('rds')
        for cluster in clusters:
            _run_cluster_method(
                client.create_db_cluster_snapshot,
                dict(
                    DBClusterSnapshotIdentifier=snapshot_identifier(
                        'Backup', cluster['DBClusterIdentifier']),
                    DBClusterIdentifier=cluster['DBClusterIdentifier']),
                (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
                client.exceptions.InvalidDBClusterStateFault)


@RDSCluster.action_registry.register('modify-db-cluster')
class ModifyDbCluster(BaseAction):
    """Modifies an RDS instance based on specified parameter
    using ModifyDbInstance.

    'Immediate" determines whether the modification is applied immediately
    or not. If 'immediate' is not specified, default is false.

    :example:

    .. code-block:: yaml

            policies:
              - name: disable-db-cluster-deletion-protection
                resource: rds-cluster
                filters:
                  - DeletionProtection: true
                  - PubliclyAccessible: true
                actions:
                  - type: modify-db-cluster
                    attributes:
                        CopyTagsToSnapshot: true
                        DeletionProtection: false
    """

    schema = type_schema(
        'modify-db-cluster',
        attributes={'type': 'object'},
        required=('attributes',))

    permissions = ('rds:ModifyDBCluster',)
    shape = 'ModifyDBClusterMessage'

    def validate(self):
        attrs = dict(self.data['attributes'])
        if 'DBClusterIdentifier' in attrs:
            raise PolicyValidationError(
                "Can't include DBClusterIdentifier in modify-db-cluster action")
        attrs['DBClusterIdentifier'] = 'PolicyValidation'
        return shape_validate(attrs, self.shape, 'rds')

    def process(self, clusters):
        client = local_session(self.manager.session_factory).client('rds')
        for c in clusters:
            client.modify_db_cluster(
                DBClusterIdentifier=c['DBClusterIdentifier'],
                **self.data['attributes'])


class DescribeClusterSnapshot(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('rds')
        return self.manager.retry(
            client.describe_db_cluster_snapshots,
            Filters=[{
                'Name': 'db-cluster-snapshot-id',
                'Values': resource_ids}]).get('DBClusterSnapshots', ())

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagList', ())
        return resources


class ConfigClusterSnapshot(ConfigSource):

    def load_resource(self, item):

        resource = super(ConfigClusterSnapshot, self).load_resource(item)
        # db cluster snapshots are particularly mangled on keys
        for k, v in list(resource.items()):
            if k.startswith('Dbcl'):
                resource.pop(k)
                k = 'DBCl%s' % k[4:]
                resource[k] = v
            elif k.startswith('Iamd'):
                resource.pop(k)
                k = 'IAMD%s' % k[4:]
                resource[k] = v
        return resource


@resources.register('rds-cluster-snapshot')
class RDSClusterSnapshot(QueryResourceManager):
    """Resource manager for RDS cluster snapshots.
    """

    class resource_type(TypeInfo):
        service = 'rds'
        arn_type = 'cluster-snapshot'
        arn_separator = ':'
        arn = 'DBClusterSnapshotArn'
        enum_spec = (
            'describe_db_cluster_snapshots', 'DBClusterSnapshots', None)
        name = id = 'DBClusterSnapshotIdentifier'
        date = 'SnapshotCreateTime'
        universal_taggable = object()
        config_type = 'AWS::RDS::DBClusterSnapshot'
        permissions_enum = ('rds:DescribeDBClusterSnapshots',)

    source_mapping = {
        'describe': DescribeClusterSnapshot,
        'config': ConfigClusterSnapshot
    }


@RDSClusterSnapshot.filter_registry.register('cross-account')
class CrossAccountSnapshot(CrossAccountAccessFilter):

    permissions = ('rds:DescribeDBClusterSnapshotAttributes',)
    attributes_key = 'c7n:attributes'
    annotation_key = 'c7n:CrossAccountViolations'

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
        self.everyone_only = self.data.get("everyone_only", False)
        results = []
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for resource_set in chunks(resources, 20):
                futures.append(w.submit(
                    self.process_resource_set, resource_set))
            for f in as_completed(futures):
                results.extend(f.result())
        return results

    def process_resource_set(self, resource_set):
        client = local_session(self.manager.session_factory).client('rds')
        results = []
        for r in resource_set:
            attrs = {t['AttributeName']: t['AttributeValues']
             for t in self.manager.retry(
                client.describe_db_cluster_snapshot_attributes,
                     DBClusterSnapshotIdentifier=r['DBClusterSnapshotIdentifier'])[
                         'DBClusterSnapshotAttributesResult']['DBClusterSnapshotAttributes']}
            r[self.attributes_key] = attrs
            shared_accounts = set(attrs.get('restore', []))
            if self.everyone_only:
                shared_accounts = {a for a in shared_accounts if a == 'all'}
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r[self.annotation_key] = list(delta_accounts)
                results.append(r)
        return results


@RDSClusterSnapshot.filter_registry.register('age')
class RDSSnapshotAge(AgeFilter):
    """Filters rds cluster snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshots-expired
                resource: rds-cluster-snapshot
                filters:
                  - type: age
                    days: 30
                    op: gt
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

    date_attribute = 'SnapshotCreateTime'


@RDSClusterSnapshot.action_registry.register('set-permissions')
class SetPermissions(rds.SetPermissions):
    """Set permissions for copying or restoring an RDS cluster snapshot

    Use the 'add' and 'remove' parameters to control which accounts to
    add or remove, respectively.  The default is to remove any
    permissions granted to other AWS accounts.

    Use `remove: matched` in combination with the `cross-account` filter
    for more flexible removal options such as preserving access for
    a set of whitelisted accounts:

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshot-prune-permissions
                resource: rds-cluster-snapshot
                filters:
                  - type: cross-account
                    whitelist:
                      - '112233445566'
                actions:
                  - type: set-permissions
                    remove: matched
    """
    permissions = ('rds:ModifyDBClusterSnapshotAttribute',)

    def process_snapshot(self, client, snapshot):
        add_accounts = self.data.get('add', [])
        remove_accounts = self.data.get('remove', [])

        if not (add_accounts or remove_accounts):
            if CrossAccountSnapshot.attributes_key not in snapshot:
                attrs = {
                    t['AttributeName']: t['AttributeValues']
                    for t in self.manager.retry(
                        client.describe_db_cluster_snapshot_attributes,
                        DBClusterSnapshotIdentifier=snapshot['DBClusterSnapshotIdentifier']
                    )['DBClusterSnapshotAttributesResult']['DBClusterSnapshotAttributes']
                }
                snapshot[CrossAccountSnapshot.attributes_key] = attrs
            remove_accounts = snapshot[CrossAccountSnapshot.attributes_key].get('restore', [])
        elif remove_accounts == 'matched':
            remove_accounts = snapshot.get(CrossAccountSnapshot.annotation_key, [])

        if add_accounts or remove_accounts:
            client.modify_db_cluster_snapshot_attribute(
                DBClusterSnapshotIdentifier=snapshot['DBClusterSnapshotIdentifier'],
                AttributeName='restore',
                ValuesToRemove=remove_accounts,
                ValuesToAdd=add_accounts)


@RDSClusterSnapshot.action_registry.register('delete')
class RDSClusterSnapshotDelete(BaseAction):
    """Action to delete rds cluster snapshots

    To prevent unwanted deletion of rds cluster snapshots, it is recommended
    to apply a filter to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-snapshots-expired-delete
                resource: rds-cluster-snapshot
                filters:
                  - type: age
                    days: 30
                    op: gt
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBClusterSnapshot',)

    def process(self, snapshots):
        self.log.info("Deleting %d RDS cluster snapshots", len(snapshots))
        client = local_session(self.manager.session_factory).client('rds')
        error = None
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, client, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    error = f.exception()
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
        if error:
            raise error
        return snapshots

    def process_snapshot_set(self, client, snapshots_set):
        for s in snapshots_set:
            try:
                client.delete_db_cluster_snapshot(
                    DBClusterSnapshotIdentifier=s['DBClusterSnapshotIdentifier'])
            except (client.exceptions.DBSnapshotNotFoundFault,
                    client.exceptions.InvalidDBSnapshotStateFault):
                continue


@RDSClusterSnapshot.action_registry.register("region-copy")
class RDSClusterSnapshotRegionCopy(BaseAction):
    """Copy an cluster snapshot across regions


    Example::

      - name: copy-encrypted-cluster-snapshots
        description: |
          copy cluster snapshots under 1 day old to dr region with kms
        resource: rds-cluster-snapshot
        region: us-east-1
        filters:
         - Status: available
         - type: value
           key: SnapshotCreateTime
           value_type: age
           value: 1
           op: less-than
        actions:
          - type: region-copy
            target_region: us-east-2
            target_key: arn:aws:kms:us-east-2:644160558196:key/b10f842a-feb7-4318-92d5-0640a75b7688
            copy_tags: true
            tags:
              OriginRegion: us-east-1
    """

    schema = type_schema(
        "region-copy",
        target_region={"type": "string"},
        target_key={"type": "string"},
        copy_tags={"type": "boolean"},
        tags={"type": "object"},
        required=("target_region",),
    )

    permissions = ("rds:CopyDBClusterSnapshot",)
    min_delay = 120
    max_attempts = 30

    def validate(self):
        if self.data.get('target_region') and self.manager.data.get('mode'):
            raise PolicyValidationError(
                "cross region snapshot may require waiting for "
                "longer then lambda runtime allows %s" % (self.manager.data,))
        return self

    def process(self, resources):
        if self.data['target_region'] == self.manager.config.region:
            self.log.warning(
                "Source and destination region are the same, skipping copy")
            return
        for resource_set in chunks(resources, 20):
            self.process_resource_set(resource_set)

    def process_resource(self, target, key, tags, snapshot):
        p = {}
        if key:
            p['KmsKeyId'] = key
        p['TargetDBClusterSnapshotIdentifier'] = snapshot[
            'DBClusterSnapshotIdentifier'].replace(':', '-')
        p['SourceRegion'] = self.manager.config.region
        p['SourceDBClusterSnapshotIdentifier'] = snapshot['DBClusterSnapshotArn']

        if self.data.get('copy_tags', True):
            p['CopyTags'] = True
        if tags:
            p['Tags'] = tags

        retry = get_retry(
            ('SnapshotQuotaExceeded',),
            # TODO make this configurable, class defaults to 1hr
            min_delay=self.min_delay,
            max_attempts=self.max_attempts,
            log_retries=logging.DEBUG)

        try:
            result = retry(target.copy_db_cluster_snapshot, **p)
        except ClientError as e:
            if e.response['Error']['Code'] == 'DBClusterSnapshotAlreadyExists':
                self.log.warning(
                    "Cluster snapshot %s already exists in target region",
                    snapshot['DBClusterSnapshotIdentifier'])
                return
            raise
        snapshot['c7n:CopiedClusterSnapshot'] = result[
            'DBClusterSnapshot']['DBClusterSnapshotArn']

    def process_resource_set(self, resource_set):
        target_client = self.manager.session_factory(
            region=self.data['target_region']).client('rds')
        target_key = self.data.get('target_key')
        tags = [{'Key': k, 'Value': v} for k, v
                in self.data.get('tags', {}).items()]

        for snapshot_set in chunks(resource_set, 5):
            for r in snapshot_set:
                # If tags are supplied, copy tags are ignored, and
                # we need to augment the tag set with the original
                # resource tags to preserve the common case.
                rtags = tags and list(tags) or None
                if tags and self.data.get('copy_tags', True):
                    rtags.extend(r['Tags'])
                self.process_resource(target_client, target_key, rtags, r)


RDSCluster.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)


@RDSCluster.filter_registry.register('consecutive-snapshots')
class ConsecutiveSnapshots(Filter):
    """Returns RDS clusters where number of consective daily snapshots is equal to/or greater
     than n days.

    :example:

    .. code-block:: yaml

            policies:
              - name: rdscluster-daily-snapshot-count
                resource: rds-cluster
                filters:
                  - type: consecutive-snapshots
                    days: 7
    """
    schema = type_schema('consecutive-snapshots', days={'type': 'number', 'minimum': 1},
        required=['days'])
    permissions = ('rds:DescribeDBClusterSnapshots', 'rds:DescribeDBClusters')
    annotation = 'c7n:DBClusterSnapshots'

    def process_resource_set(self, client, resources):
        rds_clusters = [r['DBClusterIdentifier'] for r in resources]
        paginator = client.get_paginator('describe_db_cluster_snapshots')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        cluster_snapshots = paginator.paginate(Filters=[{'Name': 'db-cluster-id',
          'Values': rds_clusters}]).build_full_result().get('DBClusterSnapshots', [])

        cluster_map = {}
        for snapshot in cluster_snapshots:
            cluster_map.setdefault(snapshot['DBClusterIdentifier'], []).append(snapshot)
        for r in resources:
            r[self.annotation] = cluster_map.get(r['DBClusterIdentifier'], [])

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('rds')
        results = []
        retention = self.data.get('days')
        utcnow = datetime.utcnow()
        expected_dates = set()
        for days in range(1, retention + 1):
            expected_dates.add((utcnow - timedelta(days=days)).strftime('%Y-%m-%d'))

        for resource_set in chunks(
                [r for r in resources if self.annotation not in r], 50):
            self.process_resource_set(client, resource_set)

        for r in resources:
            snapshot_dates = set()
            for snapshot in r[self.annotation]:
                if snapshot['Status'] == 'available':
                    snapshot_dates.add(snapshot['SnapshotCreateTime'].strftime('%Y-%m-%d'))
            if expected_dates.issubset(snapshot_dates):
                results.append(r)
        return results


@RDSCluster.filter_registry.register('db-cluster-parameter')
class ClusterParameterFilter(ParameterFilter):
    """
    Applies value type filter on set db cluster parameter values.

    :example:

    .. code-block:: yaml

            policies:
              - name: rdscluster-pg
                resource: rds-cluster
                filters:
                  - type: db-cluster-parameter
                    key: someparam
                    op: eq
                    value: someval
    """
    schema = type_schema('db-cluster-parameter', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('rds:DescribeDBInstances', 'rds:DescribeDBParameters',)
    policy_annotation = 'c7n:MatchedDBClusterParameter'
    param_group_attribute = 'DBClusterParameterGroup'

    def _get_param_list(self, pg):
        client = local_session(self.manager.session_factory).client('rds')
        paginator = client.get_paginator('describe_db_cluster_parameters')
        param_list = list(itertools.chain(*[p['Parameters']
            for p in paginator.paginate(DBClusterParameterGroupName=pg)]))
        return param_list

    def process(self, resources, event=None):
        results = []
        parameter_group_list = {db.get(self.param_group_attribute) for db in resources}
        paramcache = self.handle_paramgroup_cache(parameter_group_list)
        for resource in resources:
            pg_values = paramcache[resource['DBClusterParameterGroup']]
            if self.match(pg_values):
                resource.setdefault(self.policy_annotation, []).append(
                    self.data.get('key'))
                results.append(resource)
        return results


@RDSCluster.filter_registry.register('pending-maintenance')
class PendingMaintenance(Filter):
    """
    Scan DB Clusters for those with pending maintenance

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-pending-maintenance
                resource: rds-cluster
                filters:
                  - pending-maintenance
                  - type: value
                    key: '"c7n:PendingMaintenance".PendingMaintenanceActionDetails[].Action'
                    op: intersect
                    value:
                      - system-update
    """

    annotation_key = 'c7n:PendingMaintenance'
    schema = type_schema('pending-maintenance')
    permissions = ('rds:DescribePendingMaintenanceActions',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('rds')

        results = []
        resource_maintenances = {}
        paginator = client.get_paginator('describe_pending_maintenance_actions')
        for page in paginator.paginate():
            for action in page['PendingMaintenanceActions']:
                resource_maintenances.setdefault(action['ResourceIdentifier'], []).append(action)

        for r in resources:
            pending_maintenances = resource_maintenances.get(r['DBClusterArn'], [])
            if len(pending_maintenances) > 0:
                r[self.annotation_key] = pending_maintenances
                results.append(r)

        return results


class DescribeDbShardGroup(DescribeSource):
    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagList', ())
        return resources


@resources.register('rds-db-shard-group')
class RDSDbShardGroup(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'rds'
        arn = 'DBShardGroupArn'
        name = 'DBShardGroupIdentifier'
        id = 'DBShardGroupResourceId'
        enum_spec = ('describe_db_shard_groups', 'DBShardGroups', None)
        cfn_type = 'AWS::RDS::DBShardGroup'
        permissions_enum = ("rds:DescribeDBShardGroups",)
        universal_taggable = object()

    source_mapping = {
            'describe': DescribeDbShardGroup
        }
