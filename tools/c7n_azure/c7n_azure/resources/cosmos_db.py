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
from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
import logging
from netaddr import IPNetwork


@resources.register('cosmosdb')
class CosmosDB(ArmResourceManager):
    """Cosmos Database Resource

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
        client = 'CosmosDB'
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

    def __init__(self, data, manager=None):
        super(CosmosDBFirewallRulesFilter, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.cosmosdb')

    @property
    def log(self):
        return self._log

    def _query_rules(self, resource):

        ip_range_string = resource['properties']['ipRangeFilter']

        resource_rules = set([IPNetwork(ip_range) for ip_range in ip_range_string.split(',')])

        return resource_rules
