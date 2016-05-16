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
from c7n.filters import FilterRegistry, Filter
from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, type_schema, get_account_id

from functools import partial

log = logging.getLogger('custodian.rds')


filters = FilterRegistry('rds.filters')
actions = ActionRegistry('rds.actions')


@resources.register('rds')
class RDS(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def resources(self):
        session = local_session(self.session_factory)
        c = session.client('rds')
        query = self.resource_query()
        if self._cache.load():
            dbs = self._cache.get(
                {'resource': 'rds', 'region': self.config.region, 'q': query})
            if dbs is not None:
                self.log.debug("Using cached rds: %d" % (
                    len(dbs)))
                return self.filter_resources(dbs)
        self.log.info("Querying rds instances")
        p = c.get_paginator('describe_db_instances')
        results = p.paginate(Filters=query)
        dbs = list(itertools.chain(*[rp['DBInstances'] for rp in results]))

        _rds_tags(dbs, self.session_factory, self.executor_factory,
                  get_account_id(session), region=self.config.region)
        self._cache.save(
            {'region': self.config.region, 'resource': 'rds', 'q': query}, dbs)
        return self.filter_resources(dbs)

    def get_resources(self, resource_ids):
        c = local_session(self.session_factory).client('rds')
        results = []
        for db_id in resource_ids:
            results.extend(
                c.describe_db_instances(
                    DBInstanceIdentifier=db_id)['DBInstances'])
        _rds_tags(results)
        return results


def _rds_tags(dbs, session_factory, executor_factory, account_id, region):
    """Augment rds instances with their respective tags."""

    def process_tags(db):
        client = local_session(session_factory).client('rds')
        name = db['DBInstanceIdentifier']
        arn = "arn:aws:rds:%s:%s:db:%s" % (region, account_id, name)
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
        if v == 0 or v != self.data['days']:
            self.set_retention_window(resource)
            return resource

    def set_retention_window(self, resource):
        c = local_session(self.manager.session_factory).client('rds')
        c.modify_db_instance(
            DBInstanceIdentifier=resource['DBInstanceIdentifier'],
            BackupRetentionPeriod=self.data['days'])
