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


Todo/Notes
----------
- Tag api for rds is highly inconsistent
  compared to every other aws api, it
  requires full arns. The api never exposes
  arn. We should use a policy attribute
  for arn, that can dereference from assume
  role, instance profile role, iam user (GetUser),
  or for sts assume role users we need to
  require cli params for this resource type.

- aurora databases also generate clusters
  that are listed separately and return
  different metadata using the cluster api


"""
import logging
import itertools

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, Filter, AgeFilter
from c7n.manager import ResourceManager, resources
from c7n.query import QueryResourceManager
from c7n import tags
from c7n.utils import local_session, type_schema, get_account_id, chunks

from skew.resources.aws import rds

log = logging.getLogger('custodian.rds')

filters = FilterRegistry('rds.filters')
actions = ActionRegistry('rds.actions')

filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('rds')
class RDS(QueryResourceManager):

    class resource_type(rds.DBInstance.Meta):
        filter_name = 'DBInstanceIdentifier'

    filter_registry = filters
    action_registry = actions
    account_id = None

    def augment(self, resources):
        session = local_session(self.session_factory)
        if self.account_id is None:
            self.account_id = get_account_id(session)
        _rds_tags(
            self.query.resolve(self.resource_type),
            resources, self.session_factory, self.executor_factory,
            self.account_id, region=self.config.region)


def _rds_tags(
        model, dbs, session_factory, executor_factory, account_id, region):
    """Augment rds instances with their respective tags."""

    def process_tags(db):
        client = local_session(session_factory).client('rds')
        arn = "arn:aws:rds:%s:%s:db:%s" % (region, account_id, db[model.id])
        tag_list = client.list_tags_for_resource(ResourceName=arn)['TagList']
        db['Tags'] = tag_list or []
        return db

    # Rds maintains a low api call limit, so this can take some time :-(
    with executor_factory(max_workers=2) as w:
        list(w.map(process_tags, dbs))


@filters.register('default-vpc')
class DefaultVpc(Filter):
    """ Matches if an rds database is in the default vpc
    """

    schema = type_schema('default-vpc')

    vpcs = None
    default_vpc = None

    def __call__(self, rdb):
        vpc_id = rdb['DBSubnetGroup']['VpcId']
        if self.vpcs is None:
            self.vpcs = set((vpc_id,))
            query_vpc = vpc_id
        else:
            query_vpc = vpc_id not in self.vpcs and vpc_id or None

        if query_vpc:
            client = local_session(self.manager.session_factory).client('ec2')
            self.log.debug("querying vpc %s" % vpc_id)
            vpcs = [v['VpcId'] for v
                    in client.describe_vpcs(VpcIds=[vpc_id])['Vpcs']
                    if v['IsDefault']]
            self.vpcs.add(vpc_id)
            if not vpcs:
                return []
            self.default_vpc = vpcs.pop()
        return vpc_id == self.default_vpc and True or False


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):

    schema = type_schema(
        'mark-for-op', rinherit=tags.TagDelayedAction.schema,
        ops={'enum': ['delete', 'snapshot']})

    batch_size = 5

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        return super(TagDelayedAction, self).process(resources)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('rds')
        for r in resources:
            arn = "arn:aws:rds:%s:%s:db:%s" % (
                self.manager.config.region, self.manager.account_id,
                r['DBInstanceIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


@actions.register('tag')
class Tag(tags.Tag):

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, resources, tags):
        client = local_session(
            self.manager.session_factory).client('rds')
        for r in resources:
            arn = "arn:aws:rds:%s:%s:db:%s" % (
                self.manager.config.region, self.manager.account_id,
                r['DBInstanceIdentifier'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)


@actions.register('remove-tag')
class RemoveTag(tags.RemoveTag):

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, resources, tag_keys):
        client = local_session(
            self.manager.session_factory).client('rds')
        for r in resources:
            arn = "arn:aws:rds:%s:%s:db:%s" % (
                self.manager.config.region, self.manager.account_id,
                r['DBInstanceIdentifier'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)


@actions.register('delete')
class Delete(BaseAction):

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['delete'],
                     'skip-snapshot': {'type': 'boolean'}}
            }
        }

    def process(self, resources):
        self.skip = self.data.get('skip-snapshot', False)

        # Concurrency feels like over kill here.
        client = local_session(self.manager.session_factory).client('rds')

        for rdb in resources:
            params = dict(
                DBInstanceIdentifier=rdb['DBInstanceIdentifier'])
            if self.skip:
                params['SkipFinalSnapshot'] = True
            else:
                params[
                    'FinalDBSnapshotIdentifier'] = rdb['DBInstanceIdentifier']
            try:
                client.delete_db_instance(**params)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidDBInstanceState":
                    continue
                raise

            self.log.info("Deleted rds: %s" % rdb['DBInstanceIdentifier'])


@actions.register('snapshot')
class Snapshot(BaseAction):

    schema = {'properties': {
        'type': {
            'enum': ['snapshot']}}}

    def process(self, resources):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for resource in resources:
                futures.append(w.submit(
                    self.process_rds_snapshot,
                    resource))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception creating rds snapshot  \n %s" % (
                                f.exception()))
        return resources

    def process_rds_snapshot(self, resource):
        c = local_session(self.manager.session_factory).client('rds')
        c.create_db_snapshot(
            DBSnapshotIdentifier="Backup-%s-%s" % (
                resource['DBInstanceIdentifier'],
                resource['Engine']),
            DBInstanceIdentifier=resource['DBInstanceIdentifier'])


@actions.register('retention')
class RetentionWindow(BaseAction):

    date_attribute = "BackupRetentionPeriod"
    schema = type_schema('retention', days={'type': 'number'})

    def process(self, resources):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for resource in resources:
                futures.append(w.submit(
                    self.process_snapshot_retention,
                    resource))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception setting rds retention  \n %s" % (
                                f.exception()))

    def process_snapshot_retention(self, resource):
        v = int(resource.get('BackupRetentionPeriod', 0))
        if v == 0 or v < self.data['days']:
            self.set_retention_window(resource)
            return resource

    def set_retention_window(self, resource):
        c = local_session(self.manager.session_factory).client('rds')
        c.modify_db_instance(
            DBInstanceIdentifier=resource['DBInstanceIdentifier'],
            BackupRetentionPeriod=self.data['days'])


@resources.register('rds-snapshot')
class RDSSnapshot(ResourceManager):

    filter_registry = FilterRegistry('rds-snapshot.filters')
    action_registry = ActionRegistry('rds-snapshot.actions')

    def resources(self):
        c = self.session_factory().client('rds')
        query = self.resource_query()
        if self._cache.load():
            snaps = self._cache.get(
                {'region': self.config.region,
                 'resource': 'rds-snapshot',
                 'q': query})
            if snaps is not None:
                return self.filter_resources(snaps)
        self.log.info('Querying rds snapshots')
        p = c.get_paginator('describe_db_snapshots')
        results = p.paginate(Filters=query)
        snapshots = list(itertools.chain(*[rp['DBSnapshots'] for rp in results]))
        self._cache.save(
            {'region': self.config.region,
             'resource': 'rds-snapshot',
             'q': query}, snapshots)
        return self.filter_resources(snapshots)

@RDSSnapshot.filter_registry.register('age')
class RDSSnapshotAge(AgeFilter):

    schema = type_schema('age', days={'type': 'number'})
    date_attribute = 'SnapshotCreateTime'

@RDSSnapshot.action_registry.register('delete')
class RDSSnapshotDelete(BaseAction):

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
                            "Exception deleting snapshot set \n %s" % (
                                f.exception()))
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('rds')
        for s in snapshots_set:
            try:
                c.delete_db_snapshot(
                    DBSnapshotIdentifier=s['DBSnapshotIdentifier'])
            except ClientError as e:
                raise
