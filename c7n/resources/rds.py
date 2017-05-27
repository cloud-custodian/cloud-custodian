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
from decimal import Decimal as D, ROUND_HALF_UP

from distutils.version import LooseVersion
from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import (
    ActionRegistry, BaseAction, AutoTagUser, ModifyVpcSecurityGroupsAction)
from c7n.filters import (
    CrossAccountAccessFilter, FilterRegistry, Filter, AgeFilter, OPERATORS,
    FilterValidationError)

from c7n.filters.health import HealthEventFilter
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n import tags
from c7n.utils import (
    local_session, type_schema,
    get_retry, chunks, generate_arn, snapshot_identifier)
from c7n.resources.kms import ResourceKmsKeyAlias

log = logging.getLogger('custodian.rds')

filters = FilterRegistry('rds.filters')
actions = ActionRegistry('rds.actions')

filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)
filters.register('health-event', HealthEventFilter)
actions.register('auto-tag-user', AutoTagUser)


@resources.register('rds')
class RDS(QueryResourceManager):
    """Resource manager for RDS DB instances.
    """

    class resource_type(object):
        service = 'rds'
        type = 'db'
        enum_spec = ('describe_db_instances', 'DBInstances', None)
        id = 'DBInstanceIdentifier'
        name = 'Endpoint.Address'
        filter_name = 'DBInstanceIdentifier'
        filter_type = 'scalar'
        date = 'InstanceCreateTime'
        dimension = 'DBInstanceIdentifier'
        config_type = 'AWS::RDS::DBInstance'

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

    filter_registry = filters
    action_registry = actions
    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('rds:ListTagsForResource',)

    def __init__(self, data, options):
        super(RDS, self).__init__(data, options)

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'rds', region=self.config.region,
                account_id=self.account_id, resource_type='db', separator=':')
        return self._generate_arn

    def augment(self, dbs):
        filter(None, _rds_tags(
            self.get_model(),
            dbs, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return dbs


def _rds_tags(
        model, dbs, session_factory, executor_factory, generator, retry):
    """Augment rds instances with their respective tags."""

    def process_tags(db):
        client = local_session(session_factory).client('rds')
        arn = generator(db[model.id])
        tag_list = None
        try:
            tag_list = retry(client.list_tags_for_resource,
                             ResourceName=arn)['TagList']
        except ClientError as e:
            if e.response['Error']['Code'] not in ['DBInstanceNotFound']:
                log.warning("Exception getting rds tags  \n %s", e)
            return None
        db['Tags'] = tag_list or []
        return db

    # Rds maintains a low api call limit, so this can take some time :-(
    with executor_factory(max_workers=1) as w:
        return list(w.map(process_tags, dbs))


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
    db_instance_id = resource['DBInstanceIdentifier']
    status = resource.get('DBInstanceStatus', '')

    # If the DB instance you are deleting has a status of "Creating,"
    # you will not be able to have a final DB snapshot taken
    # If the DB instance is in a failure state with a status of "failed,"
    # "incompatible-restore," or "incompatible-network," you can only delete
    # the instance when the SkipFinalSnapshot parameter is set to "true."
    if status in ['creating', 'failed',
                  'incompatible-restore', 'incompatible-network']:
        log.debug(
            "DB instance %s is in invalid state",
            db_instance_id)
        return False

    # FinalDBSnapshotIdentifier can not be specified when deleting a
    # replica instance
    if resource.get('ReadReplicaSourceDBInstanceIdentifier', ''):
        log.debug(
            "DB instance %s is a read-replica",
            db_instance_id)
        return False
    return True


def _get_available_engine_upgrades(client, major=False):
    """Returns all extant rds engine upgrades.

    As a nested mapping of engine type to known versions
    and their upgrades.

    Defaults to minor upgrades, but configurable to major.

    Example::

      >>> _get_engine_upgrades(client)
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
    engine_versions = client.describe_db_engine_versions()['DBEngineVersions']
    for v in engine_versions:
        if not v['Engine'] in results:
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


@filters.register('default-vpc')
class DefaultVpc(net_filters.DefaultVpcBase):
    """ Matches if an rds database is in the default vpc

    :example:

        .. code-block: yaml

            policies:
              - name: default-vpc-rds
                resource: rds
                filters:
                  - default-vpc
    """
    schema = type_schema('default-vpc')

    def __call__(self, rdb):
        return self.match(rdb['DBSubnetGroup']['VpcId'])


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcSecurityGroups[].VpcSecurityGroupId"


@filters.register('kms-alias')
class KmsKeyAlias(ResourceKmsKeyAlias):

    def process(self, dbs, event=None):
        return self.get_matching_aliases(dbs)


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Mark a RDS instance for specific custodian action

    :example:

        .. code-block: yaml

            policies:
              - name: mark-for-delete
                resource: rds
                filters:
                  - type: default-vpc
                actions:
                  - type: mark-for-op
                    op: delete
                    days: 7
    """
    schema = type_schema(
        'mark-for-op', rinherit=tags.TagDelayedAction.schema)
    permissions = ('rds:AddTagsToResource',)

    batch_size = 5

    def process(self, dbs):
        return super(TagDelayedAction, self).process(dbs)

    def process_resource_set(self, dbs, tags):
        client = local_session(self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBInstanceIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


@actions.register('auto-patch')
class AutoPatch(BaseAction):
    """Toggle AutoMinorUpgrade flag on RDS instance

    'window' parameter needs to be in the format 'ddd:hh:mm-ddd:hh:mm' and
    have at least 30 minutes between start & end time.
    If 'window' is not specified, AWS will assign a random maintenance window
    to each instance selected.

    :example:

        .. code-block: yaml

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

        .. code-block: yaml

            policies:
              - name: rds-upgrade-available
                resource: rds
                filters:
                  - upgrade-available
                    major: false

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

        .. code-block: yaml

            policies:
              - name: upgrade-rds-minor
                resource: rds
                filters:
                  - name: upgrade-available
                    major: false
                actions:
                  - type: upgrade
                    major: false
                    immediate: false

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


@actions.register('tag')
@actions.register('mark')
class Tag(tags.Tag):
    """Mark/tag a RDS instance with a key/value

    :example:

        .. code-block: yaml

            policies:
              - name: rds-owner-tag
                resource: rds
                filters:
                  - "tag:OwnerName": absent
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    concurrency = 2
    batch_size = 5
    permissions = ('rds:AddTagsToResource',)

    def process_resource_set(self, dbs, ts):
        client = local_session(
            self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBInstanceIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=ts)


@actions.register('remove-tag')
@actions.register('unmark')
class RemoveTag(tags.RemoveTag):
    """Removes a tag or set of tags from RDS instances

    :example:

        .. code-block: yaml

            policies:
              - name: rds-unmark-instances
                resource: rds
                filters:
                  - "tag:ExpiredTag": present
                actions:
                  - type: unmark
                    tags: ["ExpiredTag"]
    """

    concurrency = 2
    batch_size = 5
    permissions = ('rds:RemoveTagsFromResource',)

    def process_resource_set(self, dbs, tag_keys):
        client = local_session(
            self.manager.session_factory).client('rds')
        for db in dbs:
            arn = self.manager.generate_arn(db['DBInstanceIdentifier'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


@actions.register('tag-trim')
class TagTrim(tags.TagTrim):

    permissions = ('rds:RemoveTagsFromResource',)

    def process_tag_removal(self, resource, candidates):
        client = local_session(
            self.manager.session_factory).client('rds')
        arn = self.manager.generate_arn(resource['DBInstanceIdentifier'])
        client.remove_tags_from_resource(ResourceName=arn, TagKeys=candidates)


@actions.register('delete')
class Delete(BaseAction):
    """Deletes selected RDS instances

    This will delete RDS instances. It is recommended to apply with a filter
    to avoid deleting all RDS instances in the account.

    :example:

        .. code-block: yaml

            policies:
              - name: rds-delete
                resource: rds
                filters:
                  - default-vpc
                actions:
                  - type: delete
                    skip-snapshot: true
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['delete'],
                     'skip-snapshot': {'type': 'boolean'}}
        }
    }

    permissions = ('rds:DeleteDBInstance',)

    def process(self, dbs):
        skip = self.data.get('skip-snapshot', False)
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


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Creates a manual snapshot of a RDS instance

    :example:

        .. code-block: yaml

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
                'Backup',
                resource['DBInstanceIdentifier']),
            DBInstanceIdentifier=resource['DBInstanceIdentifier'])


@actions.register('resize')
class ResizeInstance(BaseAction):
    """Change the allocated storage of an rds instance.

    :example:

       This will find databases using over 85% of their allocated
       storage, and resize them to have an additional 30% storage
       the resize here is async during the next maintenance.

       .. code-block: yaml
            policies:
              - name: rds-snapshot-retention
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

       .. code-block: yaml
            policies:
              - name: rds-snapshot-retention
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

        .. code-block: yaml

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
        retention_type = self.data['enforce', 'min'].lower()

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


@resources.register('rds-subscription')
class RDSSubscription(QueryResourceManager):

    class resource_type(object):
        service = 'rds'
        type = 'rds-subscription'
        enum_spec = (
            'describe_event_subscriptions', 'EventSubscriptionsList', None)
        name = id = "EventSubscriptionArn"
        date = "SubscriptionCreateTime"
        config_type = "AWS::DB::EventSubscription"
        dimension = None
        # SubscriptionName isn't part of describe events results?! all the
        # other subscription apis.
        # filter_name = 'SubscriptionName'
        # filter_type = 'scalar'
        filter_name = None
        filter_type = None


@resources.register('rds-snapshot')
class RDSSnapshot(QueryResourceManager):
    """Resource manager for RDS DB snapshots.
    """

    class resource_type(object):
        service = 'rds'
        type = 'rds-snapshot'
        enum_spec = ('describe_db_snapshots', 'DBSnapshots', None)
        name = id = 'DBSnapshotIdentifier'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'SnapshotCreateTime'
        config_type = "AWS::RDS::DBSnapshot"

    filter_registry = FilterRegistry('rds-snapshot.filters')
    action_registry = ActionRegistry('rds-snapshot.actions')
    filter_registry.register('marked-for-op', tags.TagActionFilter)

    _generate_arn = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn, 'rds', region=self.config.region,
                account_id=self.account_id, resource_type='snapshot',
                separator=':')
        return self._generate_arn

    def augment(self, snaps):
        filter(None, _rds_snap_tags(
            self.get_model(),
            snaps, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return snaps


def _rds_snap_tags(
        model, snaps, session_factory, executor_factory, generator, retry):
    """Augment rds snapshots with their respective tags."""

    def process_tags(snap):
        client = local_session(session_factory).client('rds')
        arn = generator(snap[model.id])
        tag_list = None
        try:
            tag_list = retry(
                client.list_tags_for_resource, ResourceName=arn)['TagList']
        except ClientError as e:
            if e.response['Error']['Code'] not in ['DBSnapshotNotFound']:
                log.error(
                    "Exception getting rds snapshot:%s tags  \n %s",
                    snap['DBSnapshotIdentifier'], e)
            return None
        snap['Tags'] = tag_list or []
        return snap

    with executor_factory(max_workers=1) as w:
        return filter(None, (w.map(process_tags, snaps)))


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

        .. code-block: yaml

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
        op={'type': 'string', 'enum': OPERATORS.keys()})

    date_attribute = 'SnapshotCreateTime'


@RDSSnapshot.action_registry.register('tag')
class RDSSnapshotTag(tags.Tag):
    """Action to tag a RDS snapshot

    :example:

        .. code-block: yaml

            policies:
              - name: rds-snapshot-add-owner
                resource: rds-snapshot
                filters:
                  - type: age
                    days: 7
                    op: le
                actions:
                  - type: tag
                    key: rds_owner
                    value: rds_owner_name
    """

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, snaps, ts):
        client = local_session(
            self.manager.session_factory).client('rds')
        for snap in snaps:
            arn = self.manager.generate_arn(snap['DBSnapshotIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=ts)


@RDSSnapshot.action_registry.register('mark-for-op')
class RDSSnapshotTagDelayedAction(tags.TagDelayedAction):
    """Mark RDS snapshot resource for an operation at a later date

    :example:

        .. code-block: yaml

            policies:
              - name: delete-stale-snapshots
                resource: rds-snapshot
                filters:
                  - type: age
                    days: 21
                    op: eq
                actions:
                  - type: mark-for-op
                    op: delete
                    days: 7
    """

    schema = type_schema(
        'mark-for-op', rinherit=tags.TagDelayedAction.schema,
        op={'enum': ['delete']})

    batch_size = 5

    def process_resource_set(self, snaps, ts):
        client = local_session(self.manager.session_factory).client('rds')
        for snap in snaps:
            arn = self.manager.generate_arn(snap['DBSnapshotIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=ts)


@RDSSnapshot.action_registry.register('remove-tag')
@RDSSnapshot.action_registry.register('unmark')
class RDSSnapshotRemoveTag(tags.RemoveTag):
    """Removes a tag/set of tags from a RDS snapshot resource

    :example:

        .. code-block: yaml

            policies:
              - name: rds-snapshot-unmark
                resource: rds-snapshot
                filters:
                  - "tag:rds_owner": present
                actions:
                  - type: remove-tag
                    tags:
                      - rds_owner
    """

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, snaps, tag_keys):
        client = local_session(
            self.manager.session_factory).client('rds')
        for snap in snaps:
            arn = self.manager.generate_arn(snap['DBSnapshotIdentifier'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


@RDSSnapshot.filter_registry.register('cross-account')
class CrossAccountAccess(CrossAccountAccessFilter):

    permissions = ('rds:DescribeDBSnapshotAttributes',)

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
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
             for t in client.describe_db_snapshot_attributes(
                DBSnapshotIdentifier=r['DBSnapshotIdentifier'])[
                    'DBSnapshotAttributesResult']['DBSnapshotAttributes']}
            r['c7n:attributes'] = attrs
            shared_accounts = set(attrs.get('restore', []))
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(r)
        return results


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
        resource: rdb-snapshot
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
              - OriginRegion: us-east-1
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
            raise FilterValidationError(
                "cross region snapshot may require waiting for "
                "longer then lambda runtime allows")
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

        .. code-block: yaml

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
        log.info("Deleting %d rds snapshots", len(snapshots))
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
            c.delete_db_snapshot(
                DBSnapshotIdentifier=s['DBSnapshotIdentifier'])


@actions.register('modify-security-groups')
class RDSModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):

    permissions = ('rds:ModifyDBInstance', 'rds:ModifyDBCluster')

    def process(self, rds_instances):
        replication_group_map = {}
        client = local_session(self.manager.session_factory).client('rds')
        groups = super(RDSModifyVpcSecurityGroups, self).get_groups(
            rds_instances, metadata_key='VpcSecurityGroupId')

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


@resources.register('rds-subnet-group')
class RDSSubnetGroup(QueryResourceManager):
    """RDS subnet group."""

    class resource_type(object):
        service = 'rds'
        type = 'rds-subnet-group'
        id = name = 'DBSubnetGroupName'
        enum_spec = (
            'describe_db_subnet_groups', 'DBSubnetGroups', None)
        filter_name = 'DBSubnetGroupName'
        filter_type = 'scalar'
        dimension = None
        date = None
