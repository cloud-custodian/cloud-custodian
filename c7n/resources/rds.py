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

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, Filter
from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, type_schema

from functools import partial

log = logging.getLogger('custodian.rds')


filters = FilterRegistry('rds.filters')
actions = ActionRegistry('rds.actions')


@resources.register('rds')
class RDS(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def resources(self):
        c = self.session_factory().client('rds')
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
        dbs = list(itertools.chain(
            *[self.get_dbs_from_result_page(c, rp) for rp in results]))
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
        return results

    def get_dbs_from_result_page(self, client, rp):
        dbs = rp['DBInstances']
        self.add_tags_to_results(client, dbs)
        return dbs

    def add_tags_to_results(self, client, dbs):
        """
        Gets the tags for each of the databases and
        adds them to the result set.
        """
        account_id = self.get_account_id()
        fn = partial(self.process_tags, account_id=account_id, client=client)
        with self.executor_factory(max_workers=3) as w:
            list(w.map(fn, dbs))

    def process_tags(self, db, **kwargs):
        region = self.get_region(db)
        name = db['DBInstanceIdentifier']
        arn = "arn:aws:rds:%s:%s:db:%s" % (region, kwargs['account_id'], name)
        tag_list = (
            kwargs['client'].list_tags_for_resource(ResourceName=arn)['TagList']
        )
        tags = []
        if tag_list:
            tags.extend(tag_list)
        db['Tags'] = tags
        return db

    def get_account_id(self):
        # TODO: This just gets a role from the current account
        # and uses its ARN as the account ARN. See notes
        # at top of file for how else we can do this
        client = self.session_factory().client('iam')
        account_id = (
            client.list_roles(MaxItems=1)['Roles'][0]['Arn'].split(":")[4]
        )
        return account_id

    def get_region(self, db):
        # get the region from the endpoint
        endpoint_parts = db['Endpoint']['Address'].split('.')

        # format is "<db-id>.<region>.rds.amazonaws.com"
        region = endpoint_parts[-4]
        return region


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
        
        
