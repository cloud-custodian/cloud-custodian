# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
from itertools import groupby

from azure.cosmos.cosmos_client import CosmosClient
from azure.cosmos.errors import HTTPFailure
from azure.mgmt.cosmosdb.models import VirtualNetworkRule

from c7n_azure import constants
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.filters import (FirewallRulesFilter, MetricFilter, FirewallBypassFilter)
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.tags import TagHelper
from c7n_azure.utils import ResourceIdParser

from concurrent.futures import as_completed
from netaddr import IPSet

from c7n.filters import ValueFilter
from c7n.utils import type_schema

from functools import lru_cache


max_workers = constants.DEFAULT_MAX_THREAD_WORKERS
log = logging.getLogger('custodian.azure.cosmosdb')
THROUGHPUT_MULTIPLIER = 100
PORTAL_IPS = ['104.42.195.92',
              '40.76.54.131',
              '52.176.6.30',
              '52.169.50.45',
              '52.187.184.26']
AZURE_CLOUD_IPS = ['0.0.0.0']  # nosec


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
        client = 'CosmosDBManagementClient'
        enum_spec = ('database_accounts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind'
        )
        resource_type = 'Microsoft.DocumentDB/databaseAccounts'


@CosmosDB.filter_registry.register('firewall-rules')
class CosmosDBFirewallRulesFilter(FirewallRulesFilter):

    def _query_rules(self, resource):
        ip_rules = resource['properties'].get('ipRules', [])

        is_virtual_network_filter_enabled = resource['properties']['isVirtualNetworkFilterEnabled']
        if ip_rules == []:
            if is_virtual_network_filter_enabled:
                return IPSet()
            else:
                return IPSet(['0.0.0.0/0'])

        parts = set([ipRule['ipAddressOrRange'] for ipRule in ip_rules])

        # Exclude magic strings representing Portal and Azure Cloud
        if set(PORTAL_IPS).issubset(parts):
            parts = parts - set(PORTAL_IPS)
        if set(AZURE_CLOUD_IPS).issubset(parts):
            parts = parts - set(AZURE_CLOUD_IPS)

        resource_rules = IPSet(filter(None, parts))
        return resource_rules


@CosmosDB.filter_registry.register('firewall-bypass')
class CosmosFirewallBypassFilter(FirewallBypassFilter):
    """
    Filters resources by the firewall bypass rules.

    :example:

    This policy will find all CosmosDB with enabled Azure Portal and Azure AzureCloud bypass rules

    .. code-block:: yaml

        policies:
          - name: cosmosdb-bypass
            resource: azure.cosmosdb
            filters:
              - type: firewall-bypass
                mode: equal
                list:
                    - AzureCloud
                    - Portal
    """

    schema = FirewallBypassFilter.schema(['AzureCloud', 'Portal'])

    def _query_bypass(self, resource):
        ip_rules = resource['properties'].get('ipRules', [])

        is_virtual_network_filter_enabled = resource['properties']['isVirtualNetworkFilterEnabled']
        if ip_rules == []:
            if is_virtual_network_filter_enabled:
                return []
            else:
                return ['AzureCloud', 'Portal']

        parts = set([ipRule['ipAddressOrRange'] for ipRule in ip_rules])

        result = []
        if set(AZURE_CLOUD_IPS).issubset(parts):
            result.append('AzureCloud')

        if set(PORTAL_IPS).issubset(parts):
            result.append('Portal')

        return result


class CosmosDBChildResource(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        doc_groups = ['Databases']

        parent_spec = ('cosmosdb', True)
        parent_manager_name = 'cosmosdb'
        raise_on_exception = False
        annotate_parent = True

        default_report_fields = (
            'id',
            '_ts',
            '_self'
        )

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

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
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


@CosmosDBDatabase.filter_registry.register('metric')
class CosmosDBDatabaseMetricFilter(MetricFilter):
    """CosmosDB Database Metric Filter

    :example:

    This policy will find cosmos db databases with less than 1000 requests per day

    .. code-block:: yaml

        policies:
          - name: low-request-databases
            description: |
              get databases with less than 1000 requests per day
            resource: azure.cosmosdb-database
            filters:
              - type: metric
                metric: TotalRequests
                op: le
                aggregation: average
                interval: P1D
                threshold: 1000
                timeframe: 72

    """
    def get_resource_id(self, resource):
        return resource['c7n:parent-id']

    def get_filter(self, resource):
        if self.filter is None:
            parent_filter = "DatabaseName eq '%s'" % resource['id']
        else:
            parent_filter = "%s and DatabaseName eq '%s'" % (self.filter, resource['id'])

        return parent_filter


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

    def tag_operation_enabled(self, resource_type):
        return True

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
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
                c['c7n:parent'] = parent_resource
                c['c7n:database'] = d['id']
                collections.append(c)

        return collections


@CosmosDBCollection.filter_registry.register('metric')
class CosmosDBCollectionMetricFilter(MetricFilter):
    """CosmosDB Collection Metric Filter

    :example:

    This policy will find cosmos db collections with less than 1000 requests per day

    .. code-block:: yaml

        policies:
          - name: low-request-collections
            description: |
              get collections with less than 1000 requests per day
            resource: azure.cosmosdb-database
            filters:
              - type: metric
                metric: TotalRequestUnits
                op: le
                aggregation: average
                interval: P1D
                threshold: 1000
                timeframe: 72

    """
    def get_resource_id(self, resource):
        return resource['c7n:parent-id']

    def get_filter(self, resource):
        container_filter = "DatabaseName eq '%s' and CollectionName eq '%s'" \
            % (resource['c7n:database'], resource['id'])

        if self.filter is not None:
            container_filter = "%s and %s" % (self.filter, container_filter)

        return container_filter


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
          - name: cosmosdb-collection-high-throughput
            resource: azure.cosmosdb-collection
            filters:
              - type: offer
                key: offerVersion
                op: eq
                value: 'V2'

    """

    schema = type_schema('offer', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        return OfferHelper.execute_in_parallel_grouped_by_account(
            resources,
            self.executor_factory,
            self.manager.get_parent_manager(),
            self._process_account_set,
            log
        )

    def _process_account_set(self, resources, data_client):
        matched = []

        try:
            # Pass each resource through the base filter
            for resource in resources:
                filtered_resource = super(CosmosDBOfferFilter, self).process(
                    [resource['c7n:offer']],
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
            self.manager.get_parent_manager(),
            self._process_account_set,
            log,
            readonly=False
        )

    def _process_account_set(self, resources, account_client):
        try:
            throughput = self.data.get('throughput')
            for resource in resources:
                self._process_resource(resource, account_client, throughput)

        except Exception as e:
            log.warning(e)

        return resources

    def _process_resource(self, resource, account_client, throughput):
        offer = resource['c7n:offer']
        new_offer = dict(offer)
        new_offer.pop('c7n:MatchedFilters', None)
        new_offer['content']['offerThroughput'] = throughput
        account_client.ReplaceOffer(offer['_self'], new_offer)


@CosmosDBCollection.action_registry.register('restore-throughput-state')
class CosmosDBRestoreStateAction(CosmosDBReplaceOfferAction):
    """CosmosDB Restore State Action

    Restores the throughput of a cosmodb collection's offer from state
    stored in a tag on the collections's parent CosmosDB account.

    :example:

    This policy will restore the state of Cosmos DB collections by retrieving the state from
    the tag 'on-hour-state' from its associated Cosmos DB account.

    .. code-block:: yaml

        policies:
          - name: restore-throughput-state
            resource: azure.cosmosdb-collection
            actions:
              - type: restore-throughput-state
                state-tag: on-hour-state

    """

    schema = type_schema(
        'restore-throughput-state',
        required=['state-tag'],
        **{
            'state-tag': {'type': 'string'}
        }
    )

    def _process_account_set(self, resources, account_client):
        try:
            parent_account = resources[0]['c7n:parent']
            tag_name = self.data.get('state-tag')
            container_states_tag_value = TagHelper.get_tag_value(
                parent_account, tag_name)

            if container_states_tag_value:
                for state in container_states_tag_value.split(';'):
                    state_data = state.split(':')
                    container_rid = state_data[0]
                    # restoring throughput size with multiplier since it was stored to save space
                    container_throughput = int(state_data[1]) * THROUGHPUT_MULTIPLIER

                    container = next((c for c in resources if c['_rid'] == container_rid), None)

                    if container:
                        self._process_resource(container, account_client, container_throughput)
            else:
                log.warning('No tag {} on parent resource, {}.'.format(
                    tag_name, parent_account))

        except Exception as e:
            log.warning(e)

        return resources


@CosmosDBCollection.action_registry.register('save-throughput-state')
class CosmosDBSaveStateAction(AzureBaseAction):
    """CosmosDB Store State Action

    Stores the throughput of collections in a tag on the parent Cosmos DB account.
    With accounts that have many collections, it's important to filter down which
    collections to store since there is a tag length limit (approx 16 collections).

    :example:

    This policy saves the throughput of collections with throughput over 400 in
    a tag called 'on-hour-state' on the parent Cosmos DB account.

    .. code-block:: yaml

        policies:
          - name: store-on-hours-state
            resource: azure.cosmosdb-collection
            filters:
              - type: offer
                key: content.offerThroughput
                op: gt
                value: 400
            actions:
              - type: save-throughput-state
                state-tag: on-hour-state

    """

    schema = type_schema(
        'save-throughput-state',
        required=['state-tag'],
        **{
            'state-tag': {'type': 'string'}
        }
    )

    TAG_VALUE_CHAR_LIMIT = 256

    def _process_resources(self, resources, event):
        OfferHelper.execute_in_parallel_grouped_by_account(
            resources,
            self.executor_factory,
            self.manager.get_parent_manager(),
            self._process_account_set,
            log
        )

    def _process_account_set(self, resources, account_client):
        account_tag_values = []
        tag_name = self.data.get('state-tag')
        cosmos_account = resources[0]['c7n:parent']

        for resource in resources:
            # dividing by multiplier to reduce string size (throughputs are multiples of 100)
            throughput = int(
                resource['c7n:offer']['content']['offerThroughput'] / THROUGHPUT_MULTIPLIER)

            account_tag_values.append('{}:{}'.format(
                resource['_rid'], throughput))

        tag_value = ';'.join(account_tag_values)

        if len(tag_value) > self.TAG_VALUE_CHAR_LIMIT:
            raise ValueError('Can not add tag, {}, on parent resource, {}, '
                             'because tag value exceeds allowed length.'
                             'Add filters to reduce number of containers.'
                             .format(tag_name, cosmos_account['name']))

        TagHelper.add_tags(self, cosmos_account, {tag_name: tag_value})
        return resources

    def _process_resource(self, resource):
        pass


class OfferHelper:

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
    def get_cosmos_data_client_for_account(account_id, account_endpoint, manager, readonly=True):
        key = CosmosDBChildResource.get_cosmos_key(
            ResourceIdParser.get_resource_group(account_id),
            ResourceIdParser.get_resource_name(account_id),
            manager.get_client(),
            readonly
        )
        data_client = CosmosClient(url_connection=account_endpoint, auth={'masterKey': key})
        return data_client

    @staticmethod
    def populate_offer_data_for_account(resources, account_data_client):
        if not resources[0].get('c7n:offer'):
            offers = list(account_data_client.ReadOffers())
            for resource in resources:
                offer = next((o for o in offers if o['resource'] == resource['_self']), None)
                resource['c7n:offer'] = offer

    @staticmethod
    def execute_in_parallel_grouped_by_account(
            resources, executor_factory, account_manager, process_resource_set, log, readonly=True):
        futures = []
        results = []
        account_grouped = OfferHelper.group_by_account(resources)

        # Process cosmos db account groups in parallel
        with executor_factory(max_workers=3) as w:
            for resource_set in account_grouped:

                account_client = OfferHelper.get_cosmos_data_client_for_account(
                    resource_set[0]['c7n:parent-id'],
                    resource_set[0]['c7n:document-endpoint'],
                    account_manager, readonly)

                OfferHelper.populate_offer_data_for_account(resource_set, account_client)
                futures.append(w.submit(process_resource_set, resource_set, account_client))

            for f in as_completed(futures):
                if f.exception():
                    log.warning(
                        "CosmosDB offer processing error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results


@CosmosDB.action_registry.register('set-firewall-rules')
class CosmosSetFirewallAction(SetFirewallAction):
    """ Set Firewall Rules Action

     Updates CosmosDB Firewall settings.  Learn about the firewall at:
     https://docs.microsoft.com/en-us/azure/cosmos-db/firewall-support

     By default the firewall rules are appended with the new values.  The ``append: False``
     flag can be used to replace the old rules with the new ones on
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

     ``append: True`` (default) ensures we only add to the existing configuration.

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
     We can do this by passing an empty array with ``append: False``

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
                append: False
                ip-rules: []


     """

    schema = type_schema(
        'set-firewall-rules',
        rinherit=SetFirewallAction.schema,
        **{
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['Portal', 'AzureCloud']}},
        }
    )

    def __init__(self, data, manager=None):
        super(CosmosSetFirewallAction, self).__init__(data, manager)
        self.rule_limit = 1000

    def _process_resource(self, resource):

        # IP rules
        existing_ip = [ip_rule['ipAddressOrRange']
                       for ip_rule in resource['properties'].get('ipRules', [])]
        if self.data.get('ip-rules') is not None:
            ip_rules = self._build_ip_rules(existing_ip, self.data.get('ip-rules', []))
        else:
            ip_rules = existing_ip

        # Bypass rules
        #  Cosmos DB does not have real bypass
        #  instead the portal UI adds values to your
        #  rules filter when you check the bypass box.
        existing_bypass = []
        if set(AZURE_CLOUD_IPS).issubset(existing_ip):
            existing_bypass.append('AzureCloud')

        if set(PORTAL_IPS).issubset(existing_ip):
            existing_bypass.append('Portal')

        # If unset, then we put the old values back in to emulate patch behavior
        bypass_rules = self.data.get('bypass-rules', existing_bypass)

        if 'Portal' in bypass_rules:
            ip_rules.extend(set(PORTAL_IPS).difference(ip_rules))
        if 'AzureCloud' in bypass_rules:
            ip_rules.extend(set(AZURE_CLOUD_IPS).difference(ip_rules))

        # If the user has too many rules raise exception
        if len(ip_rules) > self.rule_limit:
            raise ValueError("Skipped updating firewall for %s. "
                            "%s exceeds maximum rule count of %s." %
                            (resource['name'], len(ip_rules), self.rule_limit))

        # Add VNET rules
        existing_vnet = \
            [r['id'] for r in resource['properties'].get('virtualNetworkRules', [])]

        if self.data.get('virtual-network-rules') is not None:
            vnet_rules = self._build_vnet_rules(existing_vnet,
                                                self.data.get('virtual-network-rules', []))
        else:
            vnet_rules = existing_vnet

        # Workaround for bug https://git.io/fjFLY
        resource['properties']['locations'] = []
        for loc in resource['properties'].get('readLocations'):
            resource['properties']['locations'].append(
                {'location_name': loc['locationName'],
                 'failover_priority': loc['failoverPriority'],
                 'is_zone_redundant': loc.get('isZoneRedundant', False)})

        resource['properties']['ipRules'] = [{'ipAddressOrRange': ip} for ip in ip_rules]
        resource['properties']['virtualNetworkRules'] = \
            [VirtualNetworkRule(id=r) for r in vnet_rules]

        # Update resource
        self.client.database_accounts.begin_create_or_update(
            resource['resourceGroup'],
            resource['name'],
            create_update_parameters=resource
        )
