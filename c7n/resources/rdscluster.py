# Copyright 2016 Capital One Services, LLC
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
import logging
import json

from concurrent.futures import as_completed
from operator import itemgetter

from c7n.actions import ActionRegistry, BaseAction
from botocore.exceptions import ClientError
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (
    type_schema, local_session, snapshot_identifier, chunks)

log = logging.getLogger('custodian.rds-cluster')

filters = FilterRegistry('rds-cluster.filters')
actions = ActionRegistry('rds-cluster.actions')


@resources.register('rds-cluster')
class RDSCluster(QueryResourceManager):
    """Resource manager for RDS clusters.
    """

    class Meta(object):
        service = 'rds'
        type = 'rds-cluster'
        enum_spec = ('describe_db_clusters', 'DBClusters', None)
        name = id = 'DBClusterIdentifier'
        filter_name = None
        filter_type = None
        dimension = 'DBClusterIdentifier'
        date = None

    resource_type = Meta
    filter_registry = filters
    action_registry = actions


@actions.register('delete')
class Delete(BaseAction):
    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'},
                     'delete-instances': {'type': 'boolean'}})

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
            try:
                client.delete_db_cluster(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidDBClusterStateFault':
                    self.log.info(
                        'RDS cluster in invalid state: %s',
                        cluster['DBClusterIdentifier'])
                    continue
                raise

            self.log.info(
                'Deleted RDS cluster: %s',
                cluster['DBClusterIdentifier'])


@actions.register('retention')
class RetentionWindow(BaseAction):
    date_attribute = "BackupRetentionPeriod"
    # Tag copy not yet available for Aurora:
    #   https://forums.aws.amazon.com/thread.jspa?threadID=225812
    schema = type_schema(
        'retention',
        **{'days': {'type': 'number'}})

    def process(self, clusters):
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting RDS cluster retention  \n %s",
                        f.exception())

    def process_snapshot_retention(self, cluster):
        current_retention = int(cluster.get('BackupRetentionPeriod', 0))
        new_retention = self.data['days']

        if current_retention < new_retention:
            self.set_retention_window(
                cluster,
                max(current_retention, new_retention))
            return cluster

    def set_retention_window(self, cluster, retention):
        c = local_session(self.manager.session_factory).client('rds')
        c.modify_db_cluster(
            DBClusterIdentifier=cluster['DBClusterIdentifier'],
            BackupRetentionPeriod=retention,
            PreferredBackupWindow=cluster['PreferredBackupWindow'],
            PreferredMaintenanceWindow=cluster['PreferredMaintenanceWindow'])


@actions.register('snapshot')
class Snapshot(BaseAction):
    schema = type_schema('snapshot')

    def process(self, clusters):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for cluster in clusters:
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    cluster))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating RDS cluster snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, cluster):
        c = local_session(self.manager.session_factory).client('rds')
        c.create_db_cluster_snapshot(
            DBClusterSnapshotIdentifier=snapshot_identifier(
                'Backup',
                cluster['DBClusterIdentifier']),
            DBClusterIdentifier=cluster['DBClusterIdentifier'])


@resources.register('rds-cluster-snapshot')
class RDSClusterSnapshot(QueryResourceManager):
    """Resource manager for RDS cluster snapshots.
    """

    class Meta(object):
        service = 'rds'
        type = 'rds-cluster-snapshot'
        enum_spec = (
            'describe_db_cluster_snapshots', 'DBClusterSnapshots', None)
        name = id = 'DBClusterSnapshotIdentifier'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'SnapshotCreateTime'

    resource_type = Meta

    filter_registry = FilterRegistry('rdscluster-snapshot.filters')
    action_registry = ActionRegistry('rdscluster-snapshot.actions')


@RDSClusterSnapshot.filter_registry.register('age')
class RDSSnapshotAge(AgeFilter):
    schema = type_schema(
        'age', days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()})

    date_attribute = 'SnapshotCreateTime'


@RDSClusterSnapshot.action_registry.register('delete')
class RDSClusterSnapshotDelete(BaseAction):
    def process(self, snapshots):
        log.info("Deleting %d RDS cluster snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('rds')
        for s in snapshots_set:
            try:
                c.delete_db_cluster_snapshot(
                    DBClusterSnapshotIdentifier=s['DBClusterSnapshotIdentifier'])
            except ClientError as e:
                raise


@RDSClusterSnapshot.action_registry.register('restore')
class RDSClusterSnapshotRestore(BaseAction):
    schema = type_schema(
        'restore', vpc_sec_groups={'type': 'array'}, port={'type': 'number'}, db_subnet_group_name={'type': 'string'},
        snapshot_identifier={'type': 'string'})

    def process(self, resources):

        vpc_sec_groups = self.data.get('vpc-security-groups')
        port = self.data.get('port')
        db_subnet_group_name = self.data.get('db-security-group-name')
        snapshot_id = self.data.get('snapshot-identifier');

        for latest_snapshot in self.get_latest_snapshot(resources):
            client = local_session(self.manager.session_factory).client('rds')

            if vpc_sec_groups is None:
                self.log_default_value('vpc_sec_group')
            elif db_subnet_group_name is None:
                self.log_default_value('db_subnet_group_name')
            elif port is None:
                self.log_default_value('port')
            else:
                log.info('USING PARAMS PROVIDED IN POLICY')

            print 'USING SNAPSHOT FOR CLUSTER::', latest_snapshot['DBClusterIdentifier']
            print 'USING SNAPSHOT::', latest_snapshot['DBClusterSnapshotIdentifier']

            params = {'DBClusterIdentifier': latest_snapshot['DBClusterIdentifier'],
                      'SnapshotIdentifier': latest_snapshot['DBClusterSnapshotIdentifier'],
                      'Engine': latest_snapshot['Engine'],
                      'Port': port,
                      'VpcSecurityGroupIds': vpc_sec_groups,
                      'DBSubnetGroupName': db_subnet_group_name
                      }

            if snapshot_id:
                params['SnapshotIdentifier'] = snapshot_id

            try:
                client.restore_db_cluster_from_snapshot(**params)
                self.create_db_instances_within_cluster(latest_snapshot)
            except ClientError as e:
                raise

    """
      Right now im only returning the first value returned by the cli. I sort them from bottom to top then append the top
      value to the array then return the array.  I am setting this function up to handle an array of different
      cluster's snapshot, but for right now I just want to get the single cluster restore working then Ill focus on
      creating multiple rds cluster instances that have same values within an array in the policy.
    """
    @staticmethod
    def get_latest_snapshot(snapshots):

        x = []
        prev_obj = None

        for snapshot in snapshots:

            curr_obj = snapshot

            if prev_obj is None:
                prev_obj = curr_obj
                x.append(curr_obj)

            if curr_obj['DBClusterIdentifier'] == prev_obj['DBClusterIdentifier']:
                prev_obj = curr_obj
            else:
                x.append(curr_obj)
                prev_obj = curr_obj

        print x

        return x

    def create_db_instances_within_cluster(self, snapshot):

        db_instances = self.data.get('db-instances') or {}
        num_of_instances = db_instances.get('number', 1)
        db_identifier = db_instances.get('identifier', self.get_default_identifier(snapshot['DBClusterIdentifier']))
        db_size = db_instances.get('size', 'db.r3.large')
        post_fix = db_instances.get('post-fix', 'dev')

        if db_identifier is None:
            raise ClientError('MUST PROVIDE A db_identifier IN YOUR POLICY: Please delete cluster before trying again')
        if db_size is None:
            self.log_default_value('size:: default size is :: %s , which is minimum size', db_size)
        if num_of_instances is None:
            self.log_default_value('number:: number of db instances which is: %s', num_of_instances)

        for instance in xrange(0, num_of_instances):

            if instance == 0:
                new_db_identifier = db_identifier + '-' + post_fix
            else:
                new_db_identifier = db_identifier + '-' + post_fix + '-' + str(instance)

            params = {'DBClusterIdentifier': snapshot['DBClusterIdentifier'],
                      'Engine': snapshot['Engine'],
                      'DBInstanceClass': db_size,
                      'DBInstanceIdentifier': new_db_identifier,
                      }

            client = local_session(self.manager.session_factory).client('rds')

            try:
                client.create_db_instance(**params)
            except ClientError as e:
                raise

    """
    TODO: Need to delete cluster when failure on database instance creation.  Wondering how I can call the Delete class
    from within this function
    """
    def delete_cluster_on_failure(self, cluster):
        Delete(cluster)

    @staticmethod
    def get_default_identifier(cluster_identifier):
        split_cluster_id = cluster_identifier.split('-')

        length = len(split_cluster_id)
        name = split_cluster_id[0:length - 2]
        name = '-'.join(name)

        return name

    @staticmethod
    def log_default_value(policy_type):
        log.info('USING DEFAULT VALUE FOR: %s', policy_type)

