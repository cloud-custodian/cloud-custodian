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
import uuid

from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from netaddr import IPRange, IPSet, IPNetwork, IPAddress

from c7n.utils import type_schema


@resources.register('sqlserver')
class SqlServer(ArmResourceManager):
    """SQL Server Resource

    :example:

    This policy will find all SQL servers with average DTU consumption under
    10 percent over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: sqlserver-under-utilized
            resource: azure.sqlserver
            filters:
              - type: metric
                metric: dtu_consumption_percent
                op: lt
                aggregation: average
                threshold: 10
                timeframe: 72
                filter: "ElasticPoolResourceId eq '*'"
                no_data_action: include

    :example:

    This policy will find all SQL servers without any firewall rules defined.

    .. code-block:: yaml

        policies:
          - name: find-sqlserver-without-firewall-rules
            resource: azure.sqlserver
            filters:
              - type: firewall-rules
                equal: []

    :example:

    This policy will find all SQL servers allowing traffic from 1.2.2.128/25 CIDR.

    .. code-block:: yaml

        policies:
          - name: find-sqlserver-allowing-subnet
            resource: azure.sqlserver
            filters:
              - type: firewall-rules
                include: ['1.2.2.128/25']
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.sql'
        client = 'SqlManagementClient'
        enum_spec = ('servers', 'list', None)
        resource_type = 'Microsoft.Sql/servers'


@SqlServer.filter_registry.register('firewall-rules')
class SqlServerFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(SqlServerFirewallRulesFilter, self).__init__(data, manager)
        self._log = logging.getLogger('custodian.azure.sqlserver')
        self.client = None

    @property
    def log(self):
        return self._log

    def process(self, resources, event=None):
        self.client = self.manager.get_client()
        return super(SqlServerFirewallRulesFilter, self).process(resources, event)

    def _query_rules(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])

        resource_rules = IPSet()

        for r in query:
            resource_rules.add(IPRange(r.start_ip_address, r.end_ip_address))

        return resource_rules


@SqlServer.action_registry.register('set-firewall-rules')
class SqlSetFirewallAction(SetFirewallAction):
    """ Set Firewall Rules Action

     Updates SQL Server Firewalls and Virtual Networks settings.

     By default the firewall rules are replaced with the new values.  The ``append``
     flag can be used to force merging the new rules with the existing ones on
     the resource.

     You may also reference azure public cloud Service Tags by name in place of
     an IP address.  Use ``ServiceTags.`` followed by the ``name`` of any group
     from https://www.microsoft.com/en-us/download/details.aspx?id=56519.

     Note that there are firewall rule number limits and that you will likely need to
     use a regional block to fit within the limit.  The limit for storage accounts is
     200 rules.

     .. code-block:: yaml

         - type: set-firewall-rules
               bypass-rules:
                   - Logging
                   - Metrics
               ip-rules:
                   - 11.12.13.0/16
                   - ServiceTags.AppService.CentralUS


     :example:

     Find storage accounts without any firewall rules.

     Configure default-action to ``Deny`` and then allow:
     - Azure Logging and Metrics services
     - Two specific IPs
     - Two subnets

     .. code-block:: yaml

         policies:
             - name: add-storage-firewall
               resource: azure.storage

             filters:
                 - type: value
                   key: properties.networkAcls.ipRules
                   value_type: size
                   op: eq
                   value: 0

             actions:
                 - type: set-firewall-rules
                   bypass-rules:
                       - Logging
                       - Metrics
                   ip-rules:
                       - 11.12.13.0/16
                       - 21.22.23.24
                   virtual-network-rules:
                       - <subnet_resource_id>
                       - <subnet_resource_id>

     """

    schema = type_schema(
        'set-firewall-rules',
        rinherit=SetFirewallAction.schema,
        **{
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['AzureServices']}},
        }
    )

    def __init__(self, data, manager=None):
        super(SqlSetFirewallAction, self).__init__(data, manager)
        self.rule_limit = 1000
        self.ip_rules = self.data.get('ip-rules')

    def _process_resource(self, resource):
        if self.ip_rules is not None:
            old_ip_rules = self.client.firewall_rules.list_by_server(
                resource['resourceGroup'],
                resource['name'])

            old_ip_space = [IPRange(r.start_ip_address, r.end_ip_address) for r in old_ip_rules]
            new_ip_space = self._build_ip_rules(old_ip_space, self.data.get('ip-rules', []))

            # If the user has too many rules log and skip
            if len(new_ip_space) > self.rule_limit:
                raise ValueError("Skipped updating firewall for %s. "
                                 "%s exceeds maximum rule count of %s." %
                                 (resource['name'], len(new_ip_space), self.rule_limit))

            to_remove_ip_space = set(old_ip_space).difference(new_ip_space)
            for r in to_remove_ip_space:
                remove = next(i for i in old_ip_rules
                              if i.start_ip_address == r.first and i.end_ip_address == r.last)
                self.client.firewall_rules.delete(
                    resource['resourceGroup'],
                    resource['name'],
                    remove.name
                )

            to_add_ip_space = set(new_ip_space).difference(old_ip_space)
            for r in to_add_ip_space:
                net = IPNetwork(r)
                first = IPAddress(net.first)
                last = IPAddress(net.last)
                self.client.firewall_rules.create_or_update(
                    resource['resourceGroup'],
                    resource['name'],
                    "c7n-" + str(uuid.uuid4()),
                    str(first),
                    str(last)
                )
