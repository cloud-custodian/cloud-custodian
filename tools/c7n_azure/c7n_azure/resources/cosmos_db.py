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
import logging
from concurrent.futures import as_completed
from itertools import groupby

from azure.cosmos.cosmos_client import CosmosClient
from azure.cosmos.errors import HTTPFailure
from azure.mgmt.cosmosdb.models import VirtualNetworkRule
from c7n_azure import constants
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ResourceIdParser
from netaddr import IPSet

from c7n.filters import ValueFilter
from c7n.utils import type_schema

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache


max_workers = constants.DEFAULT_MAX_THREAD_WORKERS
log = logging.getLogger('azure.cosmosdb')


@resources.register('cosmosdb')
class CosmosDB(ArmResourceManager):
    """CosmosDB Account Resource

    :example:

    This policy will find all CosmosDB with 1000 or less total requests over the last 72 hours

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
        doc_groups = ['Databases']

        service = 'azure.mgmt.cosmosdb'
        client = 'CosmosDB'
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
        doc_groups = ['Databases']

        parent_spec = ('cosmosdb', True)
        parent_manager_name = 'cosmosdb'
        raise_on_exception = False
        annotate_parent = True

    @staticmethod
    @lru_cache()
    def get_cosmos_key(resource_group, resource_name, client, readonly=True):
        key_result = client.database_accounts.list_keys(
            resource_group,
            resource_name)
        return key_result.primary_readonly_master_key if readonly else key_result.primary_master_key

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


class OfferHelper(object):

    @staticmethod
    def account_key(resource):
        return resource['c7n:document-endpoint']

    @staticmethod
    def group_by_account(resources):
        # Group all resources by account because offers are queried per account not per collection
        account_sorted = sorted(resources, key=OfferHelper.account_key)
        account_grouped = [list(it) for k, it in groupby(
            account_sorted,
            OfferHelper.account_key)]

        return account_grouped

    @staticmethod
    def get_cosmos_data_client(resources, manager, readonly=True):
        cosmos_db_key = resources[0]['c7n:parent-id']
        url_connection = resources[0]['c7n:document-endpoint']

        # Get the data client keys
        key = CosmosDBChildResource.get_cosmos_key(
            ResourceIdParser.get_resource_group(cosmos_db_key),
            ResourceIdParser.get_resource_name(cosmos_db_key),
            manager.get_client(),
            readonly
        )

        # Build a data client
        data_client = CosmosClient(url_connection=url_connection, auth={'masterKey': key})
        return data_client

    @staticmethod
    def populate_offer_data(resources, manager, data_client=None):
        # Skip if offer key is present anywhere because we already
        # queried and joined offers in a previous filter instance
        if not resources[0].get('c7n:offer'):

            if not data_client:
                data_client = OfferHelper.get_cosmos_data_client(resources, manager)

            # Get the offers
            offers = list(data_client.ReadOffers())

            # Match up offers to collections
            for resource in resources:
                offer = [o for o in offers if o['resource'] == resource['_self']]
                resource['c7n:offer'] = offer

    @staticmethod
    def execute_in_parallel_grouped_by_account(
            resources, executor_factory, process_resource_set, log):
        futures = []
        results = []
        account_grouped = OfferHelper.group_by_account(resources)

        # Process database groups in parallel
        with executor_factory(max_workers=3) as w:
            for resource_set in account_grouped:
                futures.append(w.submit(process_resource_set, resource_set))

            for f in as_completed(futures):
                if f.exception():
                    log.warning(
                        "CosmosDB offer processing error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results


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
        return OfferHelper.execute_in_parallel_grouped_by_account(
            resources,
            self.executor_factory,
            self.process_resource_set,
            self.log
        )

    def process_resource_set(self, resources):
        matched = []

        try:
            OfferHelper.populate_offer_data(resources, self.manager.get_parent_manager())

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


@CosmosDBCollection.action_registry.register('replace-offer')
class CosmosDBReplaceOfferAction(AzureBaseAction):
    """CosmosDB Replace Offer Action

    Modify the throughput of a cosmodb collection's offer

    :example:

    This policy will ensure that no collections have offers with more than 400 RU/s throughput.

    .. code-block:: yaml

        policies:
          - name: limit-throughput-to-400
            resource: azure.cosmosdb-collection
            filters:
              - type: offer
                key: content.offerThroughput
                op: gt
                value: 400
            actions:
              - type: replace-offer
                throughput: 400

    """

    schema = type_schema(
        'replace-offer',
        required=['throughput'],
        **{
            'throughput': {'type': 'number'}
        }
    )

    def _process_resources(self, resources, event):
        OfferHelper.execute_in_parallel_grouped_by_account(
            resources,
            self.executor_factory,
            self._process_resource_set,
            self.log
        )

    def _process_resource_set(self, resources):
        try:

            # The offer data may not already be available
            manager = self.manager.get_parent_manager()
            data_client = OfferHelper.get_cosmos_data_client(resources, manager, readonly=False)
            OfferHelper.populate_offer_data(resources, manager, data_client)

            # Working under the assumption that there is 1 offer per collection...
            offer = resources[0]['c7n:offer'][0]
            new_offer = dict(offer)
            new_offer.pop('c7n:MatchedFilters', None)
            new_offer['content']['offerThroughput'] = self.data['throughput']
            new_offer = data_client.ReplaceOffer(offer['_self'], new_offer)
            for resource in resources:
                resource['c7n:offer'] = [new_offer]

        except Exception as e:
            log.warn(e)

        return resources

    def _process_resource(self, resource):
        # Since the offer lives on the account, not the collection, this action does not
        # apply to resources individually
        raise NotImplementedError(
            "CosmosDBReplaceOfferAction processes resources as a group, not individually")


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

        parts = ip_range_string.split(',')

        # We need to remove the 'magic string' they use for AzureCloud bypass
        if '0.0.0.0' in parts:
            parts.remove('0.0.0.0')

        resource_rules = IPSet(filter(None, parts))

        return resource_rules


@CosmosDB.action_registry.register('set-firewall-rules')
class CosmosSetFirewallAction(SetFirewallAction):
    """ Set Firewall Rules Action

     Updates CosmosDB Firewall settings.  Learn about the firewall at:
     https://docs.microsoft.com/en-us/azure/cosmos-db/firewall-support

     By default the firewall rules are replaced with the new values.  The ``append``
     flag can be used to force merging the new rules with the existing ones on
     the resource.

     You may also reference azure public cloud Service Tags by name in place of
     an IP address.  Use ``ServiceTags.`` followed by the ``name`` of any group
     from https://www.microsoft.com/en-us/download/details.aspx?id=56519.

     Note that there are firewall rule number limits.  The limit for CosmosDB is
     1000 rules (maximum tested rule count).

     .. code-block:: yaml

         - type: set-firewall-rules
               ip-rules:
                   - 11.12.13.0/16
                   - ServiceTags.AppService.CentralUS


     :example:

     Find CosmosDB accounts without any firewall rules.

     Enable the firewall and allow:
     - All Azure Cloud IP space
     - All Portal UI IP space
     - Two additional external IP ranges

     Mark ``append: True`` to ensure we only add to the existing configuration
     which in this case means we don't remove any previously configured
     vnet firewall rules.

     .. code-block:: yaml

        policies:
          - name: cosmos-firewall
            resource: azure.cosmosdb
            filters:
              # The firewall is disabled
              - type: value
                key: properties.ipRangeFilter
                value: empty
            actions:
              - type: set-firewall-rules
                append: True
                bypass-rules:
                  - AzureCloud
                  - Portal
                ip-rules:
                  - 19.0.0.0/16
                  - 20.0.1.2


     Cosmos firewalls are disabled by simply configuring them with empty values.
     We can do this with an empty action, which defaults to ``append: False``.

     .. code-block:: yaml

        policies:
          - name: cosmos-firewall-clear
            resource: azure.cosmosdb
            filters:
              # The firewall is enabled
              - not:
                - type: value
                  key: properties.ipRangeFilter
                  value: empty
            actions:
              - type: set-firewall-rules


     """
    schema = type_schema(
        'set-firewall-rules',
        required=[],
        **{
            'append': {'type': 'boolean', "default": False},
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['Portal', 'AzureCloud']}},
            'ip-rules': {'type': 'array', 'items': {'type': 'string'}},
            'virtual-network-rules': {'type': 'array', 'items': {'type': 'string'}}
        }
    )

    def __init__(self, data, manager=None):
        super(CosmosSetFirewallAction, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.cosmosdb')
        self.rule_limit = 1000

    def _process_resource(self, resource):
        existing_ip = filter(None, resource['properties'].get('ipRangeFilter', '').split(','))
        rules = self._build_ip_rules(existing_ip, self.data.get('ip-rules', []))

        # Cosmos DB does not have real bypass
        # instead the portal UI adds these values to your
        # rules filter when you check the box.
        bypass = self.data.get('bypass-rules', [])
        if 'Portal' in bypass:
            rules.extend(['104.42.195.92',
                          '40.76.54.131',
                          '52.176.6.30',
                          '52.169.50.45',
                          '52.187.184.26'])
        if 'AzureCloud' in bypass:
            rules.append('0.0.0.0')

        # If the user has too many rules log and skip
        if len(rules) > self.rule_limit:
            self._log.error("Skipped updating firewall for %s. "
                            "%s exceeds maximum rule count of %s." %
                            (resource['name'], len(rules), self.rule_limit))
            return

        # Add VNET rules
        existing_vnet = \
            [r['id'] for r in resource['properties'].get('virtualNetworkRules', [])]
        vnet_rules = self._build_vnet_rules(existing_vnet,
                                            self.data.get('virtual-network-rules', []))

        # Workaround for bug https://git.io/fjFLY
        resource['properties']['locations'] = []
        for loc in resource['properties'].get('readLocations'):
            resource['properties']['locations'].append(
                {'location_name': loc['locationName'],
                 'failover_priority': loc['failoverPriority'],
                 'is_zone_redundant': loc.get('isZoneRedundant', False)})

        resource['properties']['ipRangeFilter'] = ','.join(rules)
        resource['properties']['virtualNetworkRules'] = \
            [VirtualNetworkRule(id=r) for r in vnet_rules]

        # Update resource
        self.client.database_accounts.create_or_update(
            resource['resourceGroup'],
            resource['name'],
            create_update_parameters=resource
        )
