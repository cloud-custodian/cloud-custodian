# Copyright 2018 Capital One Services, LLC
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
from concurrent.futures import as_completed
from itertools import groupby
from netaddr import IPSet

import azure.mgmt.cosmosdb
from azure.cosmos.cosmos_client import CosmosClient
from c7n_azure import constants
from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo, ChildResourceManager
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ResourceIdParser
from azure.cosmos.errors import HTTPFailure

from c7n.filters import ValueFilter
from c7n.utils import type_schema

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache

import logging


max_workers = constants.DEFAULT_MAX_THREAD_WORKERS
log = logging.getLogger('azure.cosmosdb')


@resources.register('cosmosdb')
class CosmosDB(ArmResourceManager):
    """CosmosDB Account Resource

    :example:

    This policy will find all CosmosDB with 1000 or less total requests over the last 72 hou

    .. code-block:: yaml

        policies:
          - name: cosmosdb-inactive
            resource: azure.cosmosdb
            filters:
              - type: metric
                metric: TotalRequests
                op: le
                aggregation: total
                threshold: 1000
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.cosmosdb'
        client = 'CosmosDB'  # type: azure.mgmt.cosmosdb.CosmosDB
        enum_spec = ('database_accounts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind'
        )
        resource_type = 'Microsoft.DocumentDB/databaseAccounts'


class CosmosDBChildResource(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        parent_spec = ('cosmosdb', True)
        parent_manager_name = 'cosmosdb'
        raise_on_exception = False
        annotate_parent = True

    @staticmethod
    @lru_cache()
    def get_cosmos_key(resource_group, resource_name, client):
        key_result = client.database_accounts.get_read_only_keys(
            resource_group,
            resource_name)
        return key_result.primary_readonly_master_key

    def get_data_client(self, parent_resource):
        key = CosmosDBChildResource.get_cosmos_key(
            parent_resource['resourceGroup'],
            parent_resource.get('name'),
            self.get_parent_manager().get_client())
        data_client = CosmosClient(
            url_connection=parent_resource.get('properties').get('documentEndpoint'),
            auth={'masterKey': key})
        return data_client


@resources.register('cosmosdb-database')
class CosmosDBDatabase(CosmosDBChildResource):
    """CosmosDB Database Resource

    :example:

    This policy will enumerate all cosmos databases

    .. code-block:: yaml

        policies:
          - name: cosmosdb-database
            resource: azure.cosmosdb-database

    """

    def enumerate_resources(self, parent_resource, type_info, **params):
        data_client = self.get_data_client(parent_resource)

        try:
            databases = list(data_client.ReadDatabases())
        except HTTPFailure as e:
            if e.status_code == 403:
                log.error("403 Forbidden. Ensure identity has `Cosmos DB Account Reader` or"
                          "`DocumentDB Accounts Contributor` and that firewall is not "
                          "blocking access.")
            raise e

        for d in databases:
            d.update({'c7n:document-endpoint':
                      parent_resource.get('properties').get('documentEndpoint')})

        return databases


@resources.register('cosmosdb-collection')
class CosmosDBCollection(CosmosDBChildResource):
    """CosmosDB Collection Resource

    :example:

    This policy will find all collections with Offer Throughput > 100

    .. code-block:: yaml

        policies:
          - name: cosmosdb-high-throughput
            resource: azure.cosmosdb-collection
            filters:
              - type: offer
                key: content.offerThroughput
                op: gt
                value: 100

    """

    def enumerate_resources(self, parent_resource, type_info, **params):
        data_client = self.get_data_client(parent_resource)

        try:
            databases = list(data_client.ReadDatabases())
        except HTTPFailure as e:
            if e.status_code == 403:
                log.error("403 Forbidden. Ensure identity has `Cosmos DB Account Reader` or"
                          "`DocumentDB Accounts Contributor` and that firewall is not "
                          "blocking access.")
            raise e

        collections = []

        for d in databases:
            container_result = list(data_client.ReadContainers(d['_self']))
            for c in container_result:
                c.update({'c7n:document-endpoint':
                         parent_resource.get('properties').get('documentEndpoint')})
                collections.append(c)

        return collections


@CosmosDBCollection.filter_registry.register('offer')
@CosmosDBDatabase.filter_registry.register('offer')
class CosmosDBOfferFilter(ValueFilter):
    """CosmosDB Offer Filter

    Allows access to the offer on a collection or database.

    :example:

    This policy will find all collections with a V2 offer which indicates
    throughput is provisioned at the collection scope.

    .. code-block:: yaml

        policies:
          - name: cosmosdb-high-throughput
            resource: azure.cosmosdb-collection
            filters:
              - type: offer
                key: offerVersion
                op: eq
                value: 'V2'

    """

    schema = type_schema('offer', rinherit=ValueFilter.schema)
    schema_alias = True

    def process(self, resources, event=None):
        futures = []
        results = []

        # Group all resources by account because offers are queried per account not per collection
        account_sorted = sorted(resources, key=CosmosDBOfferFilter.account_key)
        account_grouped = [list(it) for k, it in groupby(
            account_sorted,
            CosmosDBOfferFilter.account_key)]

        # Process database groups in parallel
        with self.executor_factory(max_workers=3) as w:
            for resource_set in account_grouped:
                futures.append(w.submit(self.process_resource_set, resource_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "Offer filter error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results

    def process_resource_set(self, resources):
        matched = []

        try:
            # Skip if offer key is present anywhere because we already
            # queried and joined offers in a previous filter instance
            if not resources[0].get('c7n:offer'):

                # Get the data client keys
                parent_key = resources[0]['c7n:parent-id']
                key = CosmosDBChildResource.get_cosmos_key(
                    ResourceIdParser.get_resource_group(parent_key),
                    ResourceIdParser.get_resource_name(parent_key),
                    self.manager.get_parent_manager().get_client())

                # Build a data client
                data_client = CosmosClient(
                    url_connection=resources[0]['c7n:document-endpoint'],
                    auth={'masterKey': key})

                # Get the offers
                offers = list(data_client.ReadOffers())

                # Match up offers to collections
                for resource in resources:
                    offer = [o for o in offers if o['resource'] == resource['_self']]
                    resource['c7n:offer'] = offer

            # Pass each resource through the base filter
            for resource in resources:
                filtered_resource = super(CosmosDBOfferFilter, self).process(
                    resource['c7n:offer'],
                    event=None)

                if filtered_resource:
                    matched.append(resource)

        except Exception as error:
            log.warning(error)

        return matched

    @staticmethod
    def account_key(resource):
        return resource['c7n:document-endpoint']


@CosmosDB.filter_registry.register('firewall-rules')
class CosmosDBFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(CosmosDBFirewallRulesFilter, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.cosmosdb')

    @property
    def log(self):
        return self._log

    def _query_rules(self, resource):

        ip_range_string = resource['properties']['ipRangeFilter']

        resource_rules = IPSet(ip_range_string.split(','))

        return resource_rules
