# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
RDS Resource Manager
====================

Example Policies
----------------

Find rds instances that are publicly available

.. code-block:: yaml

   policies:
      - name: rds-public
        resource: rds
        filters:
         - PubliclyAccessible: true

Find rds instances that are not encrypted

.. code-block:: yaml

   policies:
      - name: rds-non-encrypted
        resource: rds
        filters:
         - type: value
           key: StorageEncrypted
           value: true
           op: ne

"""
import functools
import itertools
import logging
import operator
import re
import datetime

from datetime import timedelta

from decimal import Decimal as D, ROUND_HALF_UP

from c7n.vendored.distutils.version import LooseVersion
from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import (
    ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction)

from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    CrossAccountAccessFilter, FilterRegistry, Filter, ValueFilter, AgeFilter)
from c7n.filters.offhours import OffHour, OnHour
from c7n.filters import related
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager, DescribeSource, ConfigSource, TypeInfo, RetryPageIterator)
from c7n import deprecated, tags
from c7n.tags import universal_augment

from c7n.utils import (
    local_session, type_schema, get_retry, chunks, snapshot_identifier,
    merge_dict_list, filter_empty, jmespath_search)
from c7n.resources.kms import ResourceKmsKeyAlias
from c7n.resources.securityhub import PostFinding
from c7n.filters.backup import ConsecutiveAwsBackupsFilter

log = logging.getLogger('custodian.rds')

filters = FilterRegistry('rds.filters')
actions = ActionRegistry('rds.actions')


class DescribeRDS(DescribeSource):

    def augment(self, dbs):
        for d in dbs:
            d['Tags'] = d.pop('TagList', ())
        return dbs


class ConfigRDS(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        for k in list(resource.keys()):
            if k.startswith('Db'):
                resource["DB%s" % k[2:]] = resource[k]
        return resource


@resources.register('rds')
class RDS(QueryResourceManager):
    """Resource manager for RDS DB instances.
    """

    class resource_type(TypeInfo):
        service = 'rds'
        arn_type = 'db'
        arn_separator = ':'
        enum_spec = ('describe_db_instances', 'DBInstances', None)
        id = 'DBInstanceIdentifier'
        config_id = 'DbiResourceId'
        name = 'Endpoint.Address'
        filter_name = 'DBInstanceIdentifier'
        filter_type = 'scalar'
        date = 'InstanceCreateTime'
        dimension = 'DBInstanceIdentifier'
        cfn_type = config_type = 'AWS::RDS::DBInstance'
        arn = 'DBInstanceArn'
        universal_taggable = True
        default_report_fields = (
            'DBInstanceIdentifier',
            'DBName',
            'Engine',
            'EngineVersion',
            'MultiAZ',
            'AllocatedStorage',
            'StorageEncrypted',
            'PubliclyAccessible',
            'InstanceCreateTime',
        )
        permissions_enum = ('rds:DescribeDBInstances',)

    filter_registry = filters
    action_registry = actions

    def resources(self, query=None):
        if query is None and 'query' in self.data:
            query = merge_dict_list(self.data['query'])
        elif query is None:
            query = {}
        return super(RDS, self).resources(query=query)

    source_mapping = {
        'describe': DescribeRDS,
        'config': ConfigRDS
    }


def _db_instance_eligible_for_backup(resource):
    db_instance_id = resource['DBInstanceIdentifier']

    # Database instance is not in available state
    if resource.get('DBInstanceStatus', '') != 'available':
        log.debug(
            "DB instance %s is not in available state",
            db_instance_id)
        return False
    # The specified DB Instance is a member of a cluster and its
    #   backup retention should not be modified directly.  Instead,
    #   modify the backup retention of the cluster using the
    #   ModifyDbCluster API
    if resource.get('DBClusterIdentifier', ''):
        log.debug(
            "DB instance %s is a cluster member",
            db_instance_id)
        return False
    # DB Backups not supported on a read replica for engine postgres
    if (resource.get('ReadReplicaSourceDBInstanceIdentifier', '') and
            resource.get('Engine', '') == 'postgres'):
        log.debug(
            "DB instance %s is a postgres read-replica",
            db_instance_id)
        return False
    # DB Backups not supported on a read replica running a mysql
    # version before 5.6
    if (resource.get('ReadReplicaSourceDBInstanceIdentifier', '') and
            resource.get('Engine', '') == 'mysql'):
        engine_version = resource.get('EngineVersion', '')
        # Assume "<major>.<minor>.<whatever>"
        match = re.match(r'(?P<major>\d+)\.(?P<minor>\d+)\..*', engine_version)
        if (match and int(match.group('major')) < 5 or
                (int(match.group('major')) == 5 and int(match.group('minor')) < 6)):
            log.debug(
                "DB instance %s is a version %s mysql read-replica",
                db_instance_id,
                engine_version)
            return False
    return True


def _db_instance_eligible_for_final_snapshot(resource):
    status = resource.get('DBInstanceStatus', '')
    # If the DB instance you are deleting has a status of "Creating,"
    # you will not be able to have a final DB snapshot taken
    # If the DB instance is in a failure state with a status of "failed,"
    # "incompatible-restore," or "incompatible-network," you can only delete
    # the instance when the SkipFinalSnapshot parameter is set to "true."
    eligible_for_final_snapshot = True
    if status in ['creating', 'failed', 'incompatible-restore', 'incompatible-network']:
        eligible_for_final_snapshot = False

    # FinalDBSnapshotIdentifier can not be specified when deleting a
    # replica instance
    if resource.get('ReadReplicaSourceDBInstanceIdentifier', ''):
        eligible_for_final_snapshot = False

    # if it's a rds-cluster, don't try to run the rds instance snapshot api call
    if resource.get('DBClusterIdentifier', False):
        eligible_for_final_snapshot = False

    if not eligible_for_final_snapshot:
        log.debug('DB instance is not eligible for a snapshot:/n %s', resource)
    return eligible_for_final_snapshot


def _get_available_engine_upgrades(client, major=False):
    """Returns all extant rds engine upgrades.

    As a nested mapping of engine type to known versions
    and their upgrades.

    Defaults to minor upgrades, but configurable to major.

    Example::

      >>> _get_available_engine_upgrades(client)
      {
         'oracle-se2': {'12.1.0.2.v2': '12.1.0.2.v5',
                        '12.1.0.2.v3': '12.1.0.2.v5'},
         'postgres': {'9.3.1': '9.3.14',
                      '9.3.10': '9.3.14',
                      '9.3.12': '9.3.14',
                      '9.3.2': '9.3.14'}
      }
    """
    results = {}
    paginator = client.get_paginator('describe_db_engine_versions')
    for page in paginator.paginate():
        engine_versions = page['DBEngineVersions']
        for v in engine_versions:
            if v['Engine'] not in results:
                results[v['Engine']] = {}
            if 'ValidUpgradeTarget' not in v or len(v['ValidUpgradeTarget']) == 0:
                continue
            for t in v['ValidUpgradeTarget']:
                if not major and t['IsMajorVersionUpgrade']:
                    continue
                if LooseVersion(t['EngineVersion']) > LooseVersion(
                        results[v['Engine']].get(v['EngineVersion'], '0.0.0')):
                    results[v['Engine']][v['EngineVersion']] = t['EngineVersion']
    return results


filters.register('offhour', OffHour)
filters.register('onhour', OnHour)


@filters.register('default-vpc')
class DefaultVpc(net_filters.DefaultVpcBase):
    """ Matches if an rds database is in the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: default-vpc-rds
                resource: rds
                filters:
                  - type: default-vpc
    """
    schema = type_schema('default-vpc')

    def __call__(self, rdb):
        return self.match(rdb['DBSubnetGroup']['VpcId'])


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "DBSubnetGroup.Subnets[].SubnetIdentifier"


@filters.register('vpc')
class VpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "DBSubnetGroup.VpcId"


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('kms-alias')
class KmsKeyAlias(ResourceKmsKeyAlias):

    def process(self, dbs, event=None):
        return self.get_matching_aliases(dbs)


@actions.register('auto-patch')
class AutoPatch(BaseAction):
    """Toggle AutoMinorUpgrade flag on RDS instance

    'window' parameter needs to be in the format 'ddd:hh:mm-ddd:hh:mm' and
    have at least 30 minutes between start & end time.
    If 'window' is not specified, AWS will assign a random maintenance window
    to each instance selected.

    :example:

    .. code-block:: yaml

            policies:
              - name: enable-rds-autopatch
                resource: rds
                filters:
                  - AutoMinorVersionUpgrade: false
                actions:
                  - type: auto-patch
                    minor: true
                    window: Mon:23:00-Tue:01:00
    """

    schema = type_schema(
        'auto-patch',
        minor={'type': 'boolean'}, window={'type': 'string'})
    permissions = ('rds:ModifyDBInstance',)

    def process(self, dbs):
        client = local_session(
            self.manager.session_factory).client('rds')

        params = {'AutoMinorVersionUpgrade': self.data.get('minor', True)}
        if self.data.get('window'):
            params['PreferredMaintenanceWindow'] = self.data['window']

        for db in dbs:
            client.modify_db_instance(
                DBInstanceIdentifier=db['DBInstanceIdentifier'],
                **params)


@filters.register('upgrade-available')
class UpgradeAvailable(Filter):
    """ Scan DB instances for available engine upgrades

    This will pull DB instances & check their specific engine for any
    engine version with higher release numbers than the current one

    This will also annotate the rds instance with 'target_engine' which is
    the most recent version of the engine available

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-upgrade-available
                resource: rds
                filters:
                  - type: upgrade-available
                    major: False

    """

    schema = type_schema('upgrade-available',
                         major={'type': 'boolean'},
                         value={'type': 'boolean'})
    permissions = ('rds:DescribeDBEngineVersions',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('rds')
        check_upgrade_extant = self.data.get('value', True)
        check_major = self.data.get('major', False)
        engine_upgrades = _get_available_engine_upgrades(
            client, major=check_major)
        results = []

        for r in resources:
            target_upgrade = engine_upgrades.get(
                r['Engine'], {}).get(r['EngineVersion'])
            if target_upgrade is None:
                if check_upgrade_extant is False:
                    results.append(r)
                continue
            r['c7n-rds-engine-upgrade'] = target_upgrade
            results.append(r)
        return results


@actions.register('upgrade')
class UpgradeMinor(BaseAction):
    """Upgrades a RDS instance to the latest major/minor version available

    Use of the 'immediate' flag (default False) will automatically upgrade
    the RDS engine disregarding the existing maintenance window.

    :example:

    .. code-block:: yaml

            policies:
              - name: upgrade-rds-minor
                resource: rds
                actions:
                  - type: upgrade
                    major: False
                    immediate: False

    """

    schema = type_schema(
        'upgrade',
        major={'type': 'boolean'},
        immediate={'type': 'boolean'})
    permissions = ('rds:ModifyDBInstance',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        engine_upgrades = None
        for r in resources:
            if 'EngineVersion' in r['PendingModifiedValues']:
                # Upgrade has already been scheduled
                continue
            if 'c7n-rds-engine-upgrade' not in r:
                if engine_upgrades is None:
                    engine_upgrades = _get_available_engine_upgrades(
                        client, major=self.data.get('major', False))
                target = engine_upgrades.get(
                    r['Engine'], {}).get(r['EngineVersion'])
                if target is None:
                    log.debug(
                        "implicit filter no upgrade on %s",
                        r['DBInstanceIdentifier'])
                    continue
                r['c7n-rds-engine-upgrade'] = target
            client.modify_db_instance(
                DBInstanceIdentifier=r['DBInstanceIdentifier'],
                EngineVersion=r['c7n-rds-engine-upgrade'],
                ApplyImmediately=self.data.get('immediate', False))


@actions.register('tag-trim')
class TagTrim(tags.TagTrim):

    permissions = ('rds:RemoveTagsFromResource',)

    def process_tag_removal(self, client, resource, candidates):
        client.remove_tags_from_resource(ResourceName=resource['DBInstanceArn'], TagKeys=candidates)


START_STOP_ELIGIBLE_ENGINES = {
    'postgres', 'sqlserver-ee',
    'oracle-se2', 'mariadb', 'oracle-ee',
    'sqlserver-ex', 'sqlserver-se', 'oracle-se',
    'mysql', 'oracle-se1', 'sqlserver-web',
    'db2-ae', 'db2-se', 'oracle-ee-cdb',
    'sqlserver-ee', 'oracle-se2-cdb'}


def _eligible_start_stop(db, state="available"):
    # See conditions noted here
    # https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html
    # Note that this doesn't really specify what happens for all the nosql engines
    # that are available as rds engines.
    if db.get('DBInstanceStatus') != state:
        return False

    if db.get('MultiAZ') and db['Engine'].startswith('sqlserver-'):
        return False

    if db['Engine'] not in START_STOP_ELIGIBLE_ENGINES:
        return False

    if db.get('ReadReplicaDBInstanceIdentifiers'):
        return False

    if db.get('ReadReplicaSourceDBInstanceIdentifier'):
        return False

    # If the instance is part of an Aurora cluster, it can't be individually
    # stopped.
    if db.get('DBClusterIdentifier'):
        log.warning(
            (
                "DB instance %s could not be started/stopped because it's part "
                "of an Aurora cluster."
            ),
            db['DBInstanceIdentifier'],
        )
        return False

    # TODO is SQL Server mirror is detectable.
    return True


@actions.register('stop')
class Stop(BaseAction):
    """Stop an rds instance.

    https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html
    """

    schema = type_schema('stop')

    permissions = ("rds:StopDBInstance",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        for r in filter(_eligible_start_stop, resources):
            try:
                client.stop_db_instance(
                    DBInstanceIdentifier=r['DBInstanceIdentifier'])
            except ClientError as e:
                log.exception(
                    "Error stopping db instance:%s err:%s",
                    r['DBInstanceIdentifier'], e)


@actions.register('start')
class Start(BaseAction):
    """Start an rds instance.
    """

    schema = type_schema('start')

    permissions = ("rds:StartDBInstance",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        start_filter = functools.partial(_eligible_start_stop, state='stopped')
        for r in filter(start_filter, resources):
            try:
                client.start_db_instance(
                    DBInstanceIdentifier=r['DBInstanceIdentifier'])
            except ClientError as e:
                log.exception(
                    "Error starting db instance:%s err:%s",
                    r['DBInstanceIdentifier'], e)


@actions.register('delete')
class Delete(BaseAction):
    """Deletes selected RDS instances

    This will delete RDS instances. It is recommended to apply with a filter
    to avoid deleting all RDS instances in the account.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-delete
                resource: rds
                filters:
                  - default-vpc
                actions:
                  - type: delete
                    skip-snapshot: true
    """

    schema = type_schema('delete', **{
        'skip-snapshot': {'type': 'boolean'},
        'copy-restore-info': {'type': 'boolean'}
    })

    permissions = ('rds:DeleteDBInstance', 'rds:AddTagsToResource')

    def validate(self):
        if self.data.get('skip-snapshot', False) and self.data.get(
                'copy-restore-info'):
            raise PolicyValidationError(
                "skip-snapshot cannot be specified with copy-restore-info on %s" % (
                    self.manager.data,))
        return self

    def process(self, dbs):
        skip = self.data.get('skip-snapshot', False)
        # Can't delete an instance in an aurora cluster, use a policy on the cluster
        dbs = [r for r in dbs if not r.get('DBClusterIdentifier')]
        # Concurrency feels like overkill here.
        client = local_session(self.manager.session_factory).client('rds')
        for db in dbs:
            params = dict(
                DBInstanceIdentifier=db['DBInstanceIdentifier'])
            if skip or not _db_instance_eligible_for_final_snapshot(db):
                params['SkipFinalSnapshot'] = True
            else:
                params['FinalDBSnapshotIdentifier'] = snapshot_identifier(
                    'Final', db['DBInstanceIdentifier'])
            if self.data.get('copy-restore-info', False):
                self.copy_restore_info(client, db)
                if not db['CopyTagsToSnapshot']:
                    client.modify_db_instance(
                        DBInstanceIdentifier=db['DBInstanceIdentifier'],
                        CopyTagsToSnapshot=True)
            self.log.info(
                "Deleting rds: %s snapshot: %s",
                db['DBInstanceIdentifier'],
                params.get('FinalDBSnapshotIdentifier', False))

            try:
                client.delete_db_instance(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidDBInstanceState":
                    continue
                raise

        return dbs

    def copy_restore_info(self, client, instance):
        tags = []
        tags.append({
            'Key': 'VPCSecurityGroups',
            'Value': ''.join([
                g['VpcSecurityGroupId'] for g in instance['VpcSecurityGroups']
            ])})
        tags.append({
            'Key': 'OptionGroupName',
            'Value': instance['OptionGroupMemberships'][0]['OptionGroupName']})
        tags.append({
            'Key': 'ParameterGroupName',
            'Value': instance['DBParameterGroups'][0]['DBParameterGroupName']})
        tags.append({
            'Key': 'InstanceClass',
            'Value': instance['DBInstanceClass']})
        tags.append({
            'Key': 'StorageType',
            'Value': instance['StorageType']})
        tags.append({
            'Key': 'MultiAZ',
            'Value': str(instance['MultiAZ'])})
        tags.append({
            'Key': 'DBSubnetGroupName',
            'Value': instance['DBSubnetGroup']['DBSubnetGroupName']})
        client.add_tags_to_resource(
            ResourceName=self.manager.generate_arn(
                instance['DBInstanceIdentifier']),
            Tags=tags)


@actions.register('set-snapshot-copy-tags')
class CopySnapshotTags(BaseAction):
    """Enables copying tags from rds instance to snapshot

    DEPRECATED - use modify-db instead with `CopyTagsToSnapshot`

    :example:

        .. code-block:: yaml

            policies:
              - name: enable-rds-snapshot-tags
                resource: rds
                filters:
                  - type: value
                    key: Engine
                    value: aurora
                    op: eq
                actions:
                  - type: set-snapshot-copy-tags
                    enable: True
    """
    deprecations = (
        deprecated.action("use modify-db instead with `CopyTagsToSnapshot`"),
    )

    schema = type_schema(
        'set-snapshot-copy-tags',
        enable={'type': 'boolean'})
    permissions = ('rds:ModifyDBInstance',)

    def process(self, resources):
        error = None
        with self.executor_factory(max_workers=2) as w:
            futures = {}
            client = local_session(self.manager.session_factory).client('rds')
            resources = [r for r in resources
                         if r['CopyTagsToSnapshot'] != self.data.get('enable', True)]
            for r in resources:
                futures[w.submit(self.set_snapshot_tags, client, r)] = r
            for f in as_completed(futures):
                if f.exception():
                    error = f.exception()
                    self.log.error(
                        'error updating rds:%s CopyTagsToSnapshot \n %s',
                        futures[f]['DBInstanceIdentifier'], error)
        if error:
            raise error
        return resources

    def set_snapshot_tags(self, client, r):
        self.manager.retry(
            client.modify_db_instance,
            DBInstanceIdentifier=r['DBInstanceIdentifier'],
            CopyTagsToSnapshot=self.data.get('enable', True))


@RDS.action_registry.register('post-finding')
class DbInstanceFinding(PostFinding):

    resource_type = 'AwsRdsDbInstance'

    def format_resource(self, r):

        fields = [
            'AssociatedRoles', 'CACertificateIdentifier', 'DBClusterIdentifier',
            'DBInstanceIdentifier', 'DBInstanceClass', 'DbInstancePort', 'DbiResourceId',
            'DBName', 'DeletionProtection', 'Endpoint', 'Engine', 'EngineVersion',
            'IAMDatabaseAuthenticationEnabled', 'InstanceCreateTime', 'KmsKeyId',
            'PubliclyAccessible', 'StorageEncrypted',
            'TdeCredentialArn', 'VpcSecurityGroups', 'MultiAz', 'EnhancedMonitoringResourceArn',
            'DbInstanceStatus', 'MasterUsername',
            'AllocatedStorage', 'PreferredBackupWindow', 'BackupRetentionPeriod',
            'DbSecurityGroups', 'DbParameterGroups',
            'AvailabilityZone', 'DbSubnetGroup', 'PreferredMaintenanceWindow',
            'PendingModifiedValues', 'LatestRestorableTime',
            'AutoMinorVersionUpgrade', 'ReadReplicaSourceDBInstanceIdentifier',
            'ReadReplicaDBInstanceIdentifiers',
            'ReadReplicaDBClusterIdentifiers', 'LicenseModel', 'Iops', 'OptionGroupMemberships',
            'CharacterSetName',
            'SecondaryAvailabilityZone', 'StatusInfos', 'StorageType', 'DomainMemberships',
            'CopyTagsToSnapshot',
            'MonitoringInterval', 'MonitoringRoleArn', 'PromotionTier', 'Timezone',
            'PerformanceInsightsEnabled',
            'PerformanceInsightsKmsKeyId', 'PerformanceInsightsRetentionPeriod',
            'EnabledCloudWatchLogsExports',
            'ProcessorFeatures', 'ListenerEndpoint', 'MaxAllocatedStorage'
        ]
        details = {}
        for f in fields:
            if r.get(f):
                value = r[f]
                if isinstance(r[f], datetime.datetime):
                    value = r[f].isoformat()
                details.setdefault(f, value)

        db_instance = {
            'Type': self.resource_type,
            'Id': r['DBInstanceArn'],
            'Region': self.manager.config.region,
            'Tags': {t['Key']: t['Value'] for t in r.get('Tags', [])},
            'Details': {self.resource_type: filter_empty(details)},
        }
        db_instance = filter_empty(db_instance)
        return db_instance


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Creates a manual snapshot of a RDS instance

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-snapshot
                resource: rds
                actions:
                  - snapshot
    """

    schema = type_schema('snapshot')
    permissions = ('rds:CreateDBSnapshot',)

    def process(self, dbs):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for db in dbs:
                futures.append(w.submit(
                    self.process_rds_snapshot,
                    db))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating rds snapshot  \n %s",
                        f.exception())
        return dbs

    def process_rds_snapshot(self, resource):
        if not _db_instance_eligible_for_backup(resource):
            return

        c = local_session(self.manager.session_factory).client('rds')
        c.create_db_snapshot(
            DBSnapshotIdentifier=snapshot_identifier(
                self.data.get('snapshot-prefix', 'Backup'),
                resource['DBInstanceIdentifier']),
            DBInstanceIdentifier=resource['DBInstanceIdentifier'])


@actions.register('resize')
class ResizeInstance(BaseAction):
    """Change the allocated storage of an rds instance.

    :example:

    This will find databases using over 85% of their allocated
    storage, and resize them to have an additional 30% storage
    the resize here is async during the next maintenance.

    .. code-block:: yaml

            policies:
              - name: rds-resize-up
                resource: rds
                filters:
                  - type: metrics
                    name: FreeStorageSpace
                    percent-attr: AllocatedStorage
                    attr-multiplier: 1073741824
                    value: 90
                    op: greater-than
                actions:
                  - type: resize
                    percent: 30


    This will find databases using under 20% of their allocated
    storage, and resize them to be 30% smaller, the resize here
    is configured to be immediate.

    .. code-block:: yaml

            policies:
              - name: rds-resize-down
                resource: rds
                filters:
                  - type: metrics
                    name: FreeStorageSpace
                    percent-attr: AllocatedStorage
                    attr-multiplier: 1073741824
                    value: 90
                    op: greater-than
                actions:
                  - type: resize
                    percent: -30
                    immediate: true
    """
    schema = type_schema(
        'resize',
        percent={'type': 'number'},
        immediate={'type': 'boolean'})

    permissions = ('rds:ModifyDBInstance',)

    def process(self, resources):
        c = local_session(self.manager.session_factory).client('rds')
        for r in resources:
            old_val = D(r['AllocatedStorage'])
            _100 = D(100)
            new_val = ((_100 + D(self.data['percent'])) / _100) * old_val
            rounded = int(new_val.quantize(D('0'), ROUND_HALF_UP))
            c.modify_db_instance(
                DBInstanceIdentifier=r['DBInstanceIdentifier'],
                AllocatedStorage=rounded,
                ApplyImmediately=self.data.get('immediate', False))


@actions.register('retention')
class RetentionWindow(BaseAction):
    """
    Sets the 'BackupRetentionPeriod' value for automated snapshots,
    enforce (min, max, exact) sets retention days occordingly.
    :example:

    .. code-block:: yaml

            policies:
              - name: rds-snapshot-retention
                resource: rds
                filters:
                  - type: value
                    key: BackupRetentionPeriod
                    value: 7
                    op: lt
                actions:
                  - type: retention
                    days: 7
                    copy-tags: true
                    enforce: exact
    """

    date_attribute = "BackupRetentionPeriod"
    schema = type_schema(
        'retention', **{'days': {'type': 'number'},
                        'copy-tags': {'type': 'boolean'},
                        'enforce': {'type': 'string', 'enum': [
                            'min', 'max', 'exact']}})
    permissions = ('rds:ModifyDBInstance',)

    def process(self, dbs):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for db in dbs:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    db))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting rds retention  \n %s",
                        f.exception())
        return dbs

    def process_snapshot_retention(self, resource):
        current_retention = int(resource.get('BackupRetentionPeriod', 0))
        current_copy_tags = resource['CopyTagsToSnapshot']
        new_retention = self.data['days']
        new_copy_tags = self.data.get('copy-tags', True)
        retention_type = self.data.get('enforce', 'min').lower()

        if ((retention_type == 'min' or
             current_copy_tags != new_copy_tags) and
                _db_instance_eligible_for_backup(resource)):
            self.set_retention_window(
                resource,
                max(current_retention, new_retention),
                new_copy_tags)
            return resource

        if ((retention_type == 'max' or
             current_copy_tags != new_copy_tags) and
                _db_instance_eligible_for_backup(resource)):
            self.set_retention_window(
                resource,
                min(current_retention, new_retention),
                new_copy_tags)
            return resource

        if ((retention_type == 'exact' or
             current_copy_tags != new_copy_tags) and
                _db_instance_eligible_for_backup(resource)):
            self.set_retention_window(resource, new_retention, new_copy_tags)
            return resource

    def set_retention_window(self, resource, retention, copy_tags):
        c = local_session(self.manager.session_factory).client('rds')
        c.modify_db_instance(
            DBInstanceIdentifier=resource['DBInstanceIdentifier'],
            BackupRetentionPeriod=retention,
            CopyTagsToSnapshot=copy_tags)


@actions.register('set-public-access')
class RDSSetPublicAvailability(BaseAction):
    """
    This action allows for toggling an RDS instance
    'PubliclyAccessible' flag to true or false

    :example:

    .. code-block:: yaml

            policies:
              - name: disable-rds-public-accessibility
                resource: rds
                filters:
                  - PubliclyAccessible: true
                actions:
                  - type: set-public-access
                    state: false
    """

    schema = type_schema(
        "set-public-access",
        state={'type': 'boolean'})
    permissions = ('rds:ModifyDBInstance',)

    def set_accessibility(self, r):
        client = local_session(self.manager.session_factory).client('rds')
        client.modify_db_instance(
            DBInstanceIdentifier=r['DBInstanceIdentifier'],
            PubliclyAccessible=self.data.get('state', False))

    def process(self, rds):
        with self.executor_factory(max_workers=2) as w:
            futures = {w.submit(self.set_accessibility, r): r for r in rds}
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception setting public access on %s  \n %s",
                        futures[f]['DBInstanceIdentifier'], f.exception())
        return rds


@resources.register('rds-subscription')
class RDSSubscription(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'rds'
        arn_type = 'es'
        cfn_type = 'AWS::RDS::EventSubscription'
        enum_spec = (
            'describe_event_subscriptions', 'EventSubscriptionsList', None)
        name = id = "CustSubscriptionId"
        arn = 'EventSubscriptionArn'
        date = "SubscriptionCreateTime"
        permissions_enum = ('rds:DescribeEventSubscriptions',)
        universal_taggable = object()

    augment = universal_augment


@RDSSubscription.filter_registry.register('topic')
class RDSSubscriptionSNSTopic(related.RelatedResourceFilter):
    """
    Retrieves topics related to RDS event subscriptions

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-subscriptions-no-confirmed-topics
                resource: aws.rds-subscription
                filters:
                  - type: topic
                    key: SubscriptionsConfirmed
                    value: 0
                    value_type: integer
    """
    schema = type_schema('topic', rinherit=ValueFilter.schema)
    RelatedResource = 'c7n.resources.sns.SNS'
    RelatedIdsExpression = 'SnsTopicArn'
    annotation_key = 'c7n:SnsTopic'

    def process(self, resources, event=None):
        rel = self.get_related(resources)
        matched = []
        for resource in resources:
            if self.process_resource(resource, rel):
                # adding full topic details
                resource[self.annotation_key] = rel.get(
                    resource[self.RelatedIdsExpression],
                    None  # can be if value is "absent"
                )
                matched.append(resource)
        return matched


@RDSSubscription.action_registry.register('delete')
class RDSSubscriptionDelete(BaseAction):
    """Deletes a RDS snapshot resource

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-subscription-delete
                resource: rds-subscription
                filters:
                  - type: value
                    key: CustSubscriptionId
                    value: xyz
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteEventSubscription',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        for r in resources:
            self.manager.retry(
                client.delete_event_subscription, SubscriptionName=r['CustSubscriptionId'],
                ignore_err_codes=('SubscriptionNotFoundFault',
                'InvalidEventSubscriptionStateFault'))


class DescribeRDSSnapshot(DescribeSource):

    def get_resources(self, ids, cache=True):
        super_get = super().get_resources
        return list(itertools.chain(*[super_get((i,)) for i in ids]))

    def augment(self, snaps):
        for s in snaps:
            s['Tags'] = s.pop('TagList', ())
        return snaps


@resources.register('rds-snapshot')
class RDSSnapshot(QueryResourceManager):
    """Resource manager for RDS DB snapshots.
    """

    class resource_type(TypeInfo):
        service = 'rds'
        arn_type = 'snapshot'
        arn_separator = ':'
        enum_spec = ('describe_db_snapshots', 'DBSnapshots', None)
        name = id = 'DBSnapshotIdentifier'
        date = 'SnapshotCreateTime'
        config_type = "AWS::RDS::DBSnapshot"
        filter_name = "DBSnapshotIdentifier"
        filter_type = "scalar"
        universal_taggable = True
        permissions_enum = ('rds:DescribeDBSnapshots',)

    source_mapping = {
        'describe': DescribeRDSSnapshot,
        'config': ConfigSource
    }


@RDSSnapshot.filter_registry.register('onhour')
class RDSSnapshotOnHour(OnHour):
    """Scheduled action on rds snapshot."""


@RDSSnapshot.filter_registry.register('instance')
class SnapshotInstance(related.RelatedResourceFilter):
    """Filter snapshots by their database attributes.

    :example:

      Find snapshots without an extant database

    .. code-block:: yaml

       policies:
         - name: rds-snapshot-orphan
           resource: aws.rds-snapshot
           filters:
            - type: instance
              value: 0
              value_type: resource_count
    """
    schema = type_schema(
        'instance', rinherit=ValueFilter.schema
    )

    RelatedResource = "c7n.resources.rds.RDS"
    RelatedIdsExpression = "DBInstanceIdentifier"
    FetchThreshold = 5


@RDSSnapshot.filter_registry.register('latest')
class LatestSnapshot(Filter):
    """Return the latest snapshot for each database.
    """
    schema = type_schema('latest', automatic={'type': 'boolean'})
    permissions = ('rds:DescribeDBSnapshots',)

    def process(self, resources, event=None):
        results = []
        if not self.data.get('automatic', True):
            resources = [r for r in resources if r['SnapshotType'] == 'manual']
        for db_identifier, snapshots in itertools.groupby(
                resources, operator.itemgetter('DBInstanceIdentifier')):
            results.append(
                sorted(snapshots,
                       key=operator.itemgetter('SnapshotCreateTime'))[-1])
        return results


@RDSSnapshot.filter_registry.register('age')
class RDSSnapshotAge(AgeFilter):
    """Filters RDS snapshots based on age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-snapshot-expired
                resource: rds-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                actions:
                  - delete
    """

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

    date_attribute = 'SnapshotCreateTime'

    def get_resource_date(self, i):
        return i.get('SnapshotCreateTime')


@RDSSnapshot.action_registry.register('restore')
class RestoreInstance(BaseAction):
    """Restore an rds instance from a snapshot.

    Note this requires the snapshot or db deletion be taken
    with the `copy-restore-info` boolean flag set to true, as
    various instance metadata is stored on the snapshot as tags.

    additional parameters to restore db instance api call be overriden
    via `restore_options` settings. various modify db instance parameters
    can be specified via `modify_options` settings.
    """

    schema = type_schema(
        'restore',
        restore_options={'type': 'object'},
        modify_options={'type': 'object'})

    permissions = (
        'rds:ModifyDBInstance',
        'rds:ModifyDBParameterGroup',
        'rds:ModifyOptionGroup',
        'rds:RebootDBInstance',
        'rds:RestoreDBInstanceFromDBSnapshot')

    poll_period = 60
    restore_keys = {
        'VPCSecurityGroups', 'MultiAZ', 'DBSubnetGroupName',
        'InstanceClass', 'StorageType', 'ParameterGroupName',
        'OptionGroupName'}

    def validate(self):
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, LatestSnapshot):
                found = True
        if not found:
            # do we really need this...
            raise PolicyValidationError(
                "must filter by latest to use restore action %s" % (
                    self.manager.data,))
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        # restore up to 10 in parallel, we have to wait on each.
        with self.executor_factory(
                max_workers=min(10, len(resources) or 1)) as w:
            futures = {}
            for r in resources:
                tags = {t['Key']: t['Value'] for t in r['Tags']}
                if not set(tags).issuperset(self.restore_keys):
                    self.log.warning(
                        "snapshot:%s missing restore tags",
                        r['DBSnapshotIdentifier'])
                    continue
                futures[w.submit(self.process_instance, client, r)] = r
            for f in as_completed(futures):
                r = futures[f]
                if f.exception():
                    self.log.warning(
                        "Error restoring db:%s from:%s error:\n%s",
                        r['DBInstanceIdentifier'], r['DBSnapshotIdentifier'],
                        f.exception())
                    continue

    def process_instance(self, client, r):
        params, post_modify = self.get_restore_from_tags(r)
        self.manager.retry(
            client.restore_db_instance_from_db_snapshot, **params)
        waiter = client.get_waiter('db_instance_available')
        # wait up to 40m
        waiter.config.delay = self.poll_period
        waiter.wait(DBInstanceIdentifier=params['DBInstanceIdentifier'])
        self.manager.retry(
            client.modify_db_instance,
            DBInstanceIdentifier=params['DBInstanceIdentifier'],
            ApplyImmediately=True,
            **post_modify)
        self.manager.retry(
            client.reboot_db_instance,
            DBInstanceIdentifier=params['DBInstanceIdentifier'],
            ForceFailover=False)

    def get_restore_from_tags(self, snapshot):
        params, post_modify = {}, {}
        tags = {t['Key']: t['Value'] for t in snapshot['Tags']}

        params['DBInstanceIdentifier'] = snapshot['DBInstanceIdentifier']
        params['DBSnapshotIdentifier'] = snapshot['DBSnapshotIdentifier']
        params['MultiAZ'] = tags['MultiAZ'] == 'True' and True or False
        params['DBSubnetGroupName'] = tags['DBSubnetGroupName']
        params['DBInstanceClass'] = tags['InstanceClass']
        params['CopyTagsToSnapshot'] = True
        params['StorageType'] = tags['StorageType']
        params['OptionGroupName'] = tags['OptionGroupName']

        post_modify['DBParameterGroupName'] = tags['ParameterGroupName']
        post_modify['VpcSecurityGroupIds'] = tags['VPCSecurityGroups'].split(',')

        params['Tags'] = [
            {'Key': k, 'Value': v} for k, v in tags.items()
            if k not in self.restore_keys]

        params.update(self.data.get('restore_options', {}))
        post_modify.update(self.data.get('modify_options', {}))
        return params, post_modify


@RDSSnapshot.filter_registry.register('cross-account')
class CrossAccountAccess(CrossAccountAccessFilter):

    permissions = ('rds:DescribeDBSnapshotAttributes',)
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
                if f.exception():
                    self.log.error(
                        "Exception checking cross account access\n %s" % (
                            f.exception()))
                    continue
                results.extend(f.result())
        return results

    def process_resource_set(self, resource_set):
        client = local_session(self.manager.session_factory).client('rds')
        results = []
        for r in resource_set:
            attrs = {t['AttributeName']: t['AttributeValues']
             for t in self.manager.retry(
                client.describe_db_snapshot_attributes,
                DBSnapshotIdentifier=r['DBSnapshotIdentifier'])[
                    'DBSnapshotAttributesResult']['DBSnapshotAttributes']}
            r[self.attributes_key] = attrs
            shared_accounts = set(attrs.get('restore', []))
            if self.everyone_only:
                shared_accounts = {a for a in shared_accounts if a == 'all'}
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r[self.annotation_key] = list(delta_accounts)
                results.append(r)
        return results


@RDSSnapshot.action_registry.register('set-permissions')
class SetPermissions(BaseAction):
    """Set permissions for copying or restoring an RDS snapshot

    Use the 'add' and 'remove' parameters to control which accounts to
    add or remove, respectively.  The default is to remove any
    permissions granted to other AWS accounts.

    Use `remove: matched` in combination with the `cross-account` filter
    for more flexible removal options such as preserving access for
    a set of whitelisted accounts:

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-snapshot-remove-cross-account
                resource: rds-snapshot
                filters:
                  - type: cross-account
                    whitelist:
                      - '112233445566'
                actions:
                  - type: set-permissions
                    remove: matched
    """
    schema = type_schema(
        'set-permissions',
        remove={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {
                'oneOf': [
                    {'type': 'string', 'minLength': 12, 'maxLength': 12},
                    {'enum': ['all']},
                ],
            }}
        ]},
        add={
            'type': 'array', 'items': {
                'oneOf': [
                    {'type': 'string', 'minLength': 12, 'maxLength': 12},
                    {'enum': ['all']},
                ]
            }
        }
    )

    permissions = ('rds:ModifyDBSnapshotAttribute',)

    def validate(self):
        if self.data.get('remove') == 'matched':
            found = False
            for f in self.manager.iter_filters():
                if isinstance(f, CrossAccountAccessFilter):
                    found = True
                    break
            if not found:
                raise PolicyValidationError(
                    "policy:%s filter:%s with matched requires cross-account filter" % (
                        self.manager.ctx.policy.name, self.type))

    def process(self, snapshots):
        client = local_session(self.manager.session_factory).client('rds')
        for s in snapshots:
            self.process_snapshot(client, s)

    def process_snapshot(self, client, snapshot):
        add_accounts = self.data.get('add', [])
        remove_accounts = self.data.get('remove', [])

        if not (add_accounts or remove_accounts):
            if CrossAccountAccess.attributes_key not in snapshot:
                attrs = {
                    t['AttributeName']: t['AttributeValues']
                    for t in self.manager.retry(
                        client.describe_db_snapshot_attributes,
                        DBSnapshotIdentifier=snapshot['DBSnapshotIdentifier']
                    )['DBSnapshotAttributesResult']['DBSnapshotAttributes']
                }
                snapshot[CrossAccountAccess.attributes_key] = attrs
            remove_accounts = snapshot[CrossAccountAccess.attributes_key].get('restore', [])
        elif remove_accounts == 'matched':
            remove_accounts = snapshot.get(CrossAccountAccess.annotation_key, [])

        if add_accounts or remove_accounts:
            client.modify_db_snapshot_attribute(
                DBSnapshotIdentifier=snapshot['DBSnapshotIdentifier'],
                AttributeName='restore',
                ValuesToRemove=remove_accounts,
                ValuesToAdd=add_accounts)


@RDSSnapshot.action_registry.register('region-copy')
class RegionCopySnapshot(BaseAction):
    """Copy a snapshot across regions.

    Note there is a max in flight for cross region rds snapshots
    of 5 per region. This action will attempt to retry automatically
    for an hr.

    Example::

      - name: copy-encrypted-snapshots
        description: |
          copy snapshots under 1 day old to dr region with kms
        resource: rds-snapshot
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
            target_key: arn:aws:kms:us-east-2:0000:key/cb291f53-c9cf61
            copy_tags: true
            tags:
              OriginRegion: us-east-1
    """

    schema = type_schema(
        'region-copy',
        target_region={'type': 'string'},
        target_key={'type': 'string'},
        copy_tags={'type': 'boolean'},
        tags={'type': 'object'},
        required=('target_region',))

    permissions = ('rds:CopyDBSnapshot',)
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
        p['TargetDBSnapshotIdentifier'] = snapshot[
            'DBSnapshotIdentifier'].replace(':', '-')
        p['SourceRegion'] = self.manager.config.region
        p['SourceDBSnapshotIdentifier'] = snapshot['DBSnapshotArn']

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
            result = retry(target.copy_db_snapshot, **p)
        except ClientError as e:
            if e.response['Error']['Code'] == 'DBSnapshotAlreadyExists':
                self.log.warning(
                    "Snapshot %s already exists in target region",
                    snapshot['DBSnapshotIdentifier'])
                return
            raise
        snapshot['c7n:CopiedSnapshot'] = result[
            'DBSnapshot']['DBSnapshotArn']

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


@RDSSnapshot.action_registry.register('delete')
class RDSSnapshotDelete(BaseAction):
    """Deletes a RDS snapshot resource

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-snapshot-delete-stale
                resource: rds-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBSnapshot',)

    def process(self, snapshots):
        snapshots = self.filter_resources(snapshots, 'SnapshotType', ('manual',))
        if not snapshots:
            return []
        log.info("Deleting %d rds snapshots", len(snapshots))
        error = None
        with self.executor_factory(max_workers=2) as w:
            futures = []
            client = local_session(self.manager.session_factory).client('rds')
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, client, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s",
                        f.exception())
                    error = f.exception()
        if error:
            raise error
        return snapshots

    def process_snapshot_set(self, client, snapshots_set):
        for s in snapshots_set:
            try:
                self.manager.retry(
                    client.delete_db_snapshot,
                    DBSnapshotIdentifier=s['DBSnapshotIdentifier'])
            except (client.exceptions.DBSnapshotNotFoundFault,
                    client.exceptions.InvalidDBSnapshotStateFault):
                continue


@actions.register('modify-security-groups')
class RDSModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):

    permissions = ('rds:ModifyDBInstance', 'rds:ModifyDBCluster')
    vpc_expr = 'DBSubnetGroup.VpcId'

    def process(self, rds_instances):
        replication_group_map = {}
        client = local_session(self.manager.session_factory).client('rds')
        groups = super(RDSModifyVpcSecurityGroups, self).get_groups(
            rds_instances)

        # either build map for DB cluster or modify DB instance directly
        for idx, i in enumerate(rds_instances):
            if i.get('DBClusterIdentifier'):
                # build map of Replication Groups to Security Groups
                replication_group_map[i['DBClusterIdentifier']] = groups[idx]
            else:
                client.modify_db_instance(
                    DBInstanceIdentifier=i['DBInstanceIdentifier'],
                    VpcSecurityGroupIds=groups[idx])

        # handle DB cluster, if necessary
        for idx, r in enumerate(replication_group_map.keys()):
            client.modify_db_cluster(
                DBClusterIdentifier=r,
                VpcSecurityGroupIds=replication_group_map[r]
            )


class DescribeSubnetGroup(DescribeSource):

    def augment(self, resources):
        _db_subnet_group_tags(
            resources, self.manager.session_factory,
            self.manager.executor_factory, self.manager.retry)
        return resources


@resources.register('rds-subnet-group')
class RDSSubnetGroup(QueryResourceManager):
    """RDS subnet group."""

    class resource_type(TypeInfo):
        service = 'rds'
        arn_type = 'subgrp'
        id = name = 'DBSubnetGroupName'
        arn_separator = ':'
        enum_spec = (
            'describe_db_subnet_groups', 'DBSubnetGroups', None)
        filter_name = 'DBSubnetGroupName'
        filter_type = 'scalar'
        permissions_enum = ('rds:DescribeDBSubnetGroups',)
        cfn_type = config_type = 'AWS::RDS::DBSubnetGroup'
        universal_taggable = object()

    source_mapping = {
        'config': ConfigSource,
        'describe': DescribeSubnetGroup
    }


def _db_subnet_group_tags(subnet_groups, session_factory, executor_factory, retry):
    client = local_session(session_factory).client('rds')

    def process_tags(g):
        try:
            g['Tags'] = client.list_tags_for_resource(
                ResourceName=g['DBSubnetGroupArn'])['TagList']
            return g
        except client.exceptions.DBSubnetGroupNotFoundFault:
            return None

    return list(filter(None, map(process_tags, subnet_groups)))


@RDSSubnetGroup.action_registry.register('delete')
class RDSSubnetGroupDeleteAction(BaseAction):
    """Action to delete RDS Subnet Group

    It is recommended to apply a filter to the delete policy to avoid unwanted
    deletion of any rds subnet groups.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-subnet-group-delete
                resource: rds-subnet-group
                filters:
                  - Instances: []
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBSubnetGroup',)

    def process(self, subnet_group):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_subnetgroup, subnet_group))

    def process_subnetgroup(self, subnet_group):
        client = local_session(self.manager.session_factory).client('rds')
        client.delete_db_subnet_group(DBSubnetGroupName=subnet_group['DBSubnetGroupName'])


@RDSSubnetGroup.filter_registry.register('unused')
class UnusedRDSSubnetGroup(Filter):
    """Filters all launch rds subnet groups that are not in use but exist

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-subnet-group-delete-unused
                resource: rds-subnet-group
                filters:
                  - unused
    """

    schema = type_schema('unused')

    def get_permissions(self):
        return self.manager.get_resource_manager('rds').get_permissions()

    def process(self, configs, event=None):
        rds = self.manager.get_resource_manager('rds').resources()
        self.used = set(jmespath_search('[].DBSubnetGroup.DBSubnetGroupName', rds))
        self.used.update(set(jmespath_search('[].DBSubnetGroup.DBSubnetGroupName',
            self.manager.get_resource_manager('rds-cluster').resources(augment=False))))
        return super(UnusedRDSSubnetGroup, self).process(configs)

    def __call__(self, config):
        return config['DBSubnetGroupName'] not in self.used


@filters.register('db-parameter')
class ParameterFilter(ValueFilter):
    """
    Applies value type filter on set db parameter values.
    :example:

    .. code-block:: yaml

            policies:
              - name: rds-pg
                resource: rds
                filters:
                  - type: db-parameter
                    key: someparam
                    op: eq
                    value: someval
    """

    schema = type_schema('db-parameter', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('rds:DescribeDBInstances', 'rds:DescribeDBParameters', )
    policy_annotation = 'c7n:MatchedDBParameter'

    @staticmethod
    def recast(val, datatype):
        """ Re-cast the value based upon an AWS supplied datatype
            and treat nulls sensibly.
        """
        ret_val = val
        if datatype == 'string':
            ret_val = str(val)
        elif datatype == 'boolean':
            # AWS returns 1s and 0s for boolean for most of the cases
            if val.isdigit():
                ret_val = bool(int(val))
            # AWS returns 'TRUE,FALSE' for Oracle engine
            elif val == 'TRUE':
                ret_val = True
            elif val == 'FALSE':
                ret_val = False
        elif datatype == 'integer':
            if val.isdigit():
                ret_val = int(val)
        elif datatype == 'float':
            ret_val = float(val) if val else 0.0

        return ret_val

    # Private method for 'DBParameterGroupName' paginator
    def _get_param_list(self, pg):
        client = local_session(self.manager.session_factory).client('rds')
        paginator = client.get_paginator('describe_db_parameters')
        param_list = list(itertools.chain(*[p['Parameters']
            for p in paginator.paginate(DBParameterGroupName=pg)]))
        return param_list

    def handle_paramgroup_cache(self, param_groups):
        pgcache = {}
        cache = self.manager._cache

        with cache:
            for pg in param_groups:
                cache_key = {
                    'region': self.manager.config.region,
                    'account_id': self.manager.config.account_id,
                    'rds-pg': pg}
                pg_values = cache.get(cache_key)
                if pg_values is not None:
                    pgcache[pg] = pg_values
                    continue
                param_list = self._get_param_list(pg)
                pgcache[pg] = {
                    p['ParameterName']: self.recast(p['ParameterValue'], p['DataType'])
                    for p in param_list if 'ParameterValue' in p}
                cache.save(cache_key, pgcache[pg])
        return pgcache

    def process(self, resources, event=None):
        results = []
        parameter_group_list = {db['DBParameterGroups'][0]['DBParameterGroupName']
                    for db in resources}
        paramcache = self.handle_paramgroup_cache(parameter_group_list)
        for resource in resources:
            for pg in resource['DBParameterGroups']:
                pg_values = paramcache[pg['DBParameterGroupName']]
                if self.match(pg_values):
                    resource.setdefault(self.policy_annotation, []).append(
                        self.data.get('key'))
                    results.append(resource)
                    break
        return results


@actions.register('modify-db')
class ModifyDb(BaseAction):
    """Modifies an RDS instance based on specified parameter
    using ModifyDbInstance.

    'Update' is an array with with key value pairs that should be set to
    the property and value you wish to modify.
    'Immediate" determines whether the modification is applied immediately
    or not. If 'immediate' is not specified, default is false.

    :example:

    .. code-block:: yaml

            policies:
              - name: disable-rds-deletion-protection
                resource: rds
                filters:
                  - DeletionProtection: true
                  - PubliclyAccessible: true
                actions:
                  - type: modify-db
                    update:
                      - property: 'DeletionProtection'
                        value: false
                      - property: 'PubliclyAccessible'
                        value: false
                    immediate: true
    """

    schema = type_schema(
        'modify-db',
        immediate={"type": 'boolean'},
        update={
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'property': {'type': 'string', 'enum': [
                        'AllocatedStorage',
                        'DBInstanceClass',
                        'DBSubnetGroupName',
                        'DBSecurityGroups',
                        'VpcSecurityGroupIds',
                        'MasterUserPassword',
                        'DBParameterGroupName',
                        'BackupRetentionPeriod',
                        'PreferredBackupWindow',
                        'PreferredMaintenanceWindow',
                        'MultiAZ',
                        'EngineVersion',
                        'AllowMajorVersionUpgrade',
                        'AutoMinorVersionUpgrade',
                        'LicenseModel',
                        'Iops',
                        'OptionGroupName',
                        'NewDBInstanceIdentifier',
                        'StorageType',
                        'TdeCredentialArn',
                        'TdeCredentialPassword',
                        'CACertificateIdentifier',
                        'Domain',
                        'CopyTagsToSnapshot',
                        'MonitoringInterval',
                        'MonitoringRoleARN',
                        'DBPortNumber',
                        'PubliclyAccessible',
                        'DomainIAMRoleName',
                        'PromotionTier',
                        'EnableIAMDatabaseAuthentication',
                        'EnablePerformanceInsights',
                        'PerformanceInsightsKMSKeyId',
                        'PerformanceInsightsRetentionPeriod',
                        'CloudwatchLogsExportConfiguration',
                        'ProcessorFeatures',
                        'UseDefaultProcessorFeatures',
                        'DeletionProtection',
                        'MaxAllocatedStorage',
                        'CertificateRotationRestart']},
                    'value': {}
                },
            },
        },
        required=('update',))

    permissions = ('rds:ModifyDBInstance',)
    conversion_map = {
        'DBSubnetGroupName': 'DBSubnetGroup.DBSubnetGroupName',
        'VpcSecurityGroupIds': 'VpcSecurityGroups[].VpcSecurityGroupId',
        'DBParameterGroupName': 'DBParameterGroups[].DBParameterGroupName',
        'OptionGroupName': 'OptionGroupMemberships[].OptionGroupName',
        'NewDBInstanceIdentifier': 'DBInstanceIdentifier',
        'Domain': 'DomainMemberships[].DomainName',
        'DBPortNumber': 'Endpoint.Port',
        'EnablePerformanceInsights': 'PerformanceInsightsEnabled',
        'CloudwatchLogsExportConfiguration': 'EnabledCloudwatchLogsExports'
    }

    def validate(self):
        if self.data.get('update'):
            update_dict = dict((i['property'], i['value']) for i in self.data.get('update'))
            if ('MonitoringInterval' in update_dict and update_dict['MonitoringInterval'] > 0 and
                    'MonitoringRoleARN' not in update_dict):
                raise PolicyValidationError(
                    "A MonitoringRoleARN value is required \
                    if you specify a MonitoringInterval value other than 0")
            if ('CloudwatchLogsExportConfiguration' in update_dict
                and all(
                    k not in update_dict.get('CloudwatchLogsExportConfiguration')
                    for k in ('EnableLogTypes', 'DisableLogTypes'))):
                raise PolicyValidationError(
                    "A EnableLogTypes or DisableLogTypes input list is required\
                    for setting CloudwatchLogsExportConfiguration")
        return self

    def process(self, resources):
        c = local_session(self.manager.session_factory).client('rds')
        for r in resources:
            param = {
                u['property']: u['value'] for u in self.data.get('update')
                if r.get(
                    u['property'],
                    jmespath_search(
                        self.conversion_map.get(u['property'], 'None'), r))
                    != u['value']}
            if not param:
                continue
            param['ApplyImmediately'] = self.data.get('immediate', False)
            param['DBInstanceIdentifier'] = r['DBInstanceIdentifier']
            try:
                c.modify_db_instance(**param)
            except c.exceptions.DBInstanceNotFoundFault:
                raise


@resources.register('rds-reserved')
class ReservedRDS(QueryResourceManager):
    """Lists all active rds reservations

    :example:

    .. code-block:: yaml

            policies:
              - name: existing-rds-reservations
                resource: rds-reserved
                filters:
                    - State: active
    """

    class resource_type(TypeInfo):
        service = 'rds'
        name = id = 'ReservedDBInstanceId'
        date = 'StartTime'
        enum_spec = (
            'describe_reserved_db_instances', 'ReservedDBInstances', None)
        filter_name = 'ReservedDBInstances'
        filter_type = 'list'
        arn_type = "ri"
        arn = "ReservedDBInstanceArn"
        permissions_enum = ('rds:DescribeReservedDBInstances',)
        universal_taggable = object()

    augment = universal_augment


RDS.filter_registry.register('consecutive-aws-backups', ConsecutiveAwsBackupsFilter)


@filters.register('consecutive-snapshots')
class ConsecutiveSnapshots(Filter):
    """Returns instances where number of consective daily snapshots is
    equal to/or greater than n days.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-daily-snapshot-count
                resource: rds
                filters:
                  - type: consecutive-snapshots
                    days: 7
    """
    schema = type_schema('consecutive-snapshots', days={'type': 'number', 'minimum': 1},
        required=['days'])
    permissions = ('rds:DescribeDBSnapshots', 'rds:DescribeDBInstances')
    annotation = 'c7n:DBSnapshots'

    def process_resource_set(self, client, resources):
        rds_instances = [r['DBInstanceIdentifier'] for r in resources]
        paginator = client.get_paginator('describe_db_snapshots')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        db_snapshots = paginator.paginate(Filters=[{'Name': 'db-instance-id',
          'Values': rds_instances}]).build_full_result().get('DBSnapshots', [])

        inst_map = {}
        for snapshot in db_snapshots:
            inst_map.setdefault(snapshot['DBInstanceIdentifier'], []).append(snapshot)
        for r in resources:
            r[self.annotation] = inst_map.get(r['DBInstanceIdentifier'], [])

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('rds')
        results = []
        retention = self.data.get('days')
        utcnow = datetime.datetime.utcnow()
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


@filters.register('engine')
class EngineFilter(ValueFilter):
    """
    Filter a rds resource based on its Engine Metadata

    :example:

    .. code-block:: yaml

        policies:
            - name: find-deprecated-versions
              resource: aws.rds
              filters:
                - type: engine
                  key: Status
                  value: deprecated
    """

    schema = type_schema('engine', rinherit=ValueFilter.schema)

    permissions = ("rds:DescribeDBEngineVersions", )

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('rds')

        engines = set()
        engine_versions = set()
        for r in resources:
            engines.add(r['Engine'])
            engine_versions.add(r['EngineVersion'])

        paginator = client.get_paginator('describe_db_engine_versions')
        response = paginator.paginate(
            Filters=[
                {'Name': 'engine', 'Values': list(engines)},
                {'Name': 'engine-version', 'Values': list(engine_versions)}
            ],
            IncludeAll=True,
        )
        all_versions = {}
        matched = []
        for page in response:
            for e in page['DBEngineVersions']:
                all_versions.setdefault(e['Engine'], {})
                all_versions[e['Engine']][e['EngineVersion']] = e
        for r in resources:
            v = all_versions[r['Engine']][r['EngineVersion']]
            if self.match(v):
                r['c7n:Engine'] = v
                matched.append(r)
        return matched


class DescribeDBProxy(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('rds-proxy')
class RDSProxy(QueryResourceManager):
    """Resource Manager for RDS DB Proxies

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-proxy-tls-check
                resource: rds-proxy
                filters:
                  - type: value
                    key: RequireTLS
                    value: false
    """

    class resource_type(TypeInfo):
        service = 'rds'
        name = id = 'DBProxyName'
        date = 'CreatedDate'
        enum_spec = ('describe_db_proxies', 'DBProxies', None)
        arn = 'DBProxyArn'
        arn_type = 'db-proxy'
        cfn_type = 'AWS::RDS::DBProxy'
        permissions_enum = ('rds:DescribeDBProxies',)
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeDBProxy,
        'config': ConfigSource
    }


@RDSProxy.action_registry.register('delete')
class DeleteRDSProxy(BaseAction):
    """
    Deletes a RDS Proxy

    :example:

    .. code-block:: yaml

      policies:
        - name: delete-rds-proxy
          resource: aws.rds-proxy
          filters:
            - type: value
              key: "DBProxyName"
              op: eq
              value: "proxy-test-1"
          actions:
            - type: delete
    """

    schema = type_schema('delete')

    permissions = ('rds:DeleteDBProxy',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('rds')
        for r in resources:
            self.manager.retry(
                client.delete_db_proxy, DBProxyName=r['DBProxyName'],
                ignore_err_codes=('DBProxyNotFoundFault',
                'InvalidDBProxyStateFault'))


@RDSProxy.filter_registry.register('subnet')
class RDSProxySubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "VpcSubnetIds[]"


@RDSProxy.filter_registry.register('security-group')
class RDSProxySecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroupIds[]"


@RDSProxy.filter_registry.register('vpc')
class RDSProxyVpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@filters.register('db-option-groups')
class DbOptionGroups(ValueFilter):
    """This filter describes RDS option groups for associated RDS instances.
    Use this filter in conjunction with jmespath and value filter operators
    to filter RDS instance based on their option groups

    :example:

    .. code-block:: yaml

        policies:
          - name: rds-data-in-transit-encrypted
            resource: aws.rds
            filters:
              - type: db-option-groups
                key: Options[].OptionName
                op: intersect
                value:
                  - SSL
                  - NATIVE_NETWORK_ENCRYPTION

    :example:

    .. code-block:: yaml

        policies:
          - name: rds-oracle-encryption-in-transit
            resource: aws.rds
            filters:
              - Engine: oracle-ee
              - type: db-option-groups
                key: Options[].OptionSettings[?Name == 'SQLNET.ENCRYPTION_SERVER'].Value[]
                value:
                  - REQUIRED
    """

    schema = type_schema('db-option-groups', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('rds:DescribeDBInstances', 'rds:DescribeOptionGroups', )
    policy_annotation = 'c7n:MatchedDBOptionGroups'

    def handle_optiongroup_cache(self, client, paginator, option_groups):
        ogcache = {}
        cache = self.manager._cache

        with cache:
            for og in option_groups:
                cache_key = {
                    'region': self.manager.config.region,
                    'account_id': self.manager.config.account_id,
                    'rds-pg': og}
                og_values = cache.get(cache_key)
                if og_values is not None:
                    ogcache[og] = og_values
                    continue
                option_groups_list = list(itertools.chain(*[p['OptionGroupsList']
                    for p in paginator.paginate(OptionGroupName=og)]))

                ogcache[og] = {}
                for option_group in option_groups_list:
                    ogcache[og] = option_group

                cache.save(cache_key, ogcache[og])

        return ogcache

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('rds')
        paginator = client.get_paginator('describe_option_groups')
        option_groups = [db['OptionGroupMemberships'][0]['OptionGroupName']
                        for db in resources]
        optioncache = self.handle_optiongroup_cache(client, paginator, option_groups)

        for resource in resources:
            for og in resource['OptionGroupMemberships']:
                og_values = optioncache[og['OptionGroupName']]
                if self.match(og_values):
                    resource.setdefault(self.policy_annotation, []).append({
                        k: jmespath_search(k, og_values)
                        for k in {'OptionGroupName', self.data.get('key')}
                    })
                    results.append(resource)
                    break

        return results


@filters.register('pending-maintenance')
class PendingMaintenance(Filter):
    """Scan DB instances for those with pending maintenance

    :example:

    .. code-block:: yaml

        policies:
          - name: rds-pending-maintenance
            resource: aws.rds
            filters:
              - pending-maintenance
              - type: value
                key: '"c7n:PendingMaintenance"[].PendingMaintenanceActionDetails[].Action'
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
            pending_maintenances = resource_maintenances.get(r['DBInstanceArn'], [])
            if len(pending_maintenances) > 0:
                r[self.annotation_key] = pending_maintenances
                results.append(r)

        return results
