# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from concurrent.futures import as_completed
from datetime import datetime
from dateutil.tz import tzutc

from c7n.actions import BaseAction
from c7n.filters import AgeFilter, CrossAccountAccessFilter
from c7n.filters.offhours import OffHour, OnHour
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n import tags
from .aws import shape_validate
from c7n.exceptions import PolicyValidationError
from c7n.utils import (
    type_schema, local_session, snapshot_identifier, chunks)

log = logging.getLogger('custodian.rds-cluster')


class DescribeCluster(DescribeSource):

    def augment(self, resources):
        return tags.universal_augment(self.manager, resources)


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
        dimension = 'DBClusterIdentifier'
        universal_taggable = True
        permissions_enum = ('rds:DescribeDBClusters',)
        cfn_type = config_type = 'AWS::RDS::DBCluster'

    source_mapping = {
        'config': ConfigSource,
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
        _run_cluster_method(
            client.modify_db_cluster,
            dict(DBClusterIdentifier=cluster['DBClusterIdentifier'],
                 BackupRetentionPeriod=retention,
                 PreferredBackupWindow=cluster['PreferredBackupWindow'],
                 PreferredMaintenanceWindow=cluster['PreferredMaintenanceWindow']),
            (client.exceptions.DBClusterNotFoundFault, client.exceptions.ResourceNotFoundFault),
            client.exceptions.InvalidDBClusterStateFault)


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
        return tags.universal_augment(self.manager, resources)


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
        resource['Tags'] = [{'Key': k, 'Value': v} for k, v in item['tags'].items()]

        utc = tzutc()
        resource['SnapshotCreateTime'] = datetime.fromtimestamp(
            resource['SnapshotCreateTime'] / 1000, tz=utc)
        resource['ClusterCreateTime'] = datetime.fromtimestamp(
            resource['ClusterCreateTime'] / 1000, tz=utc)
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

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
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
            r['c7n:attributes'] = attrs
            shared_accounts = set(attrs.get('restore', []))
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r['c7n:CrossAccountViolations'] = list(delta_accounts)
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
