# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid

from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.filters import FirewallRulesFilter, FirewallBypassFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ThreadHelper
from netaddr import IPRange, IPSet, IPNetwork, IPAddress

from c7n.utils import type_schema
from c7n.filters.core import ValueFilter, Filter

AZURE_SERVICES = IPRange('0.0.0.0', '0.0.0.0')  # nosec
log = logging.getLogger('custodian.azure.sql-server')


@resources.register('sql-server', aliases=['sqlserver'])
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

        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind'
        )


@SqlServer.filter_registry.register('azure-ad-administrators')
class AzureADAdministratorsFilter(ValueFilter):
    """
    Provides a value filter targetting the Azure AD Administrator of this
    SQL Server.

    Here is an example of the available fields:

    .. code-block:: json

      "administratorType": "ActiveDirectory",
      "login": "bob@contoso.com",
      "sid": "00000011-1111-2222-2222-123456789111",
      "tenantId": "00000011-1111-2222-2222-123456789111",
      "azureADOnlyAuthentication": true

    :examples:

    Find SQL Servers without AD Administrator

    .. code-block:: yaml

        policies:
          - name: sqlserver-no-ad-admin
            resource: azure.sqlserver
            filters:
              - type: azure-ad-administrators
                key: login
                value: absent

    """

    schema = type_schema('azure-ad-administrators', rinherit=ValueFilter.schema)

    def __call__(self, i):
        if 'administrators' not in i['properties']:
            client = self.manager.get_client()
            administrators = list(
                client.server_azure_ad_administrators
                .list_by_server(i['resourceGroup'], i['name'])
            )

            # This matches the expanded schema, and despite the name
            # there can only be a single administrator, not an array.
            if administrators:
                i['properties']['administrators'] = \
                    administrators[0].serialize(True).get('properties', {})
            else:
                i['properties']['administrators'] = {}

        return super(AzureADAdministratorsFilter, self).__call__(i['properties']['administrators'])


@SqlServer.filter_registry.register('vulnerability-assessment')
class VulnerabilityAssessmentFilter(Filter):
    """
    Filter sql servers by whether they have recurring vulnerability scans
    enabled.

    :example:

    Find SQL servers without vulnerability assessments enabled.

    .. code-block:: yaml

        policies:
          - name: sql-server-no-va
            resource: azure.sql-server
            filters:
              - type: vulnerability-assessment
                enabled: false

    """

    schema = type_schema(
        'vulnerability-assessment',
        required=['type', 'enabled'],
        **{
            'enabled': {"type": "boolean"},
        }
    )

    log = logging.getLogger('custodian.azure.sqldatabase.vulnerability-assessment-filter')

    def __init__(self, data, manager=None):
        super(VulnerabilityAssessmentFilter, self).__init__(data, manager)
        self.enabled = self.data['enabled']

    def process(self, resources, event=None):
        resources, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )
        if exceptions:
            raise exceptions[0]
        return resources

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client()
        result = []
        for resource in resources:
            if 'c7n:vulnerability_assessment' not in resource['properties']:
                va = list(client.server_vulnerability_assessments.list_by_server(
                    resource['resourceGroup'],
                    resource['name']))

                # there can only be a single instance named "Default".
                if va:
                    resource['c7n:vulnerability_assessment'] = \
                        va[0].serialize(True).get('properties', {})
                else:
                    resource['c7n:vulnerability_assessment'] = {}

            if resource['c7n:vulnerability_assessment']\
                    .get('recurringScans', {})\
                    .get('isEnabled', False) == self.enabled:
                result.append(resource)

        return result


@SqlServer.filter_registry.register('firewall-rules')
class SqlServerFirewallRulesFilter(FirewallRulesFilter):
    def _query_rules(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])

        resource_rules = IPSet()

        for r in query:
            rule = IPRange(r.start_ip_address, r.end_ip_address)
            if rule == AZURE_SERVICES:
                # Ignore 0.0.0.0 magic value representing Azure Cloud bypass
                continue
            resource_rules.add(rule)

        return resource_rules


@SqlServer.filter_registry.register('firewall-bypass')
class SqlServerFirewallBypassFilter(FirewallBypassFilter):
    """
    Filters resources by the firewall bypass rules.

    :example:

    This policy will find all SQL Servers with enabled Azure Services bypass rules

    .. code-block:: yaml

        policies:
          - name: sqlserver-bypass
            resource: azure.sqlserver
            filters:
              - type: firewall-bypass
                mode: equal
                list:
                    - AzureServices
    """

    schema = FirewallBypassFilter.schema(['AzureServices'])

    def _query_bypass(self, resource):
        # Remove spaces from the string for the comparision
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])

        for r in query:
            if r.start_ip_address == '0.0.0.0' and r.end_ip_address == '0.0.0.0':  # nosec
                return ['AzureServices']
        return []


@SqlServer.action_registry.register('set-firewall-rules')
class SqlSetFirewallAction(SetFirewallAction):
    """ Set Firewall Rules Action

     Updates SQL Server Firewall configuration.

     By default the firewall rules are replaced with the new values.  The ``append``
     flag can be used to force merging the new rules with the existing ones on
     the resource.

     You may also reference azure public cloud Service Tags by name in place of
     an IP address.  Use ``ServiceTags.`` followed by the ``name`` of any group
     from https://www.microsoft.com/en-us/download/details.aspx?id=56519.

     .. code-block:: yaml

         - type: set-firewall-rules
               bypass-rules:
                   - AzureServices
               ip-rules:
                   - 11.12.13.0/16
                   - ServiceTags.AppService.CentralUS


     :example:

     Configure firewall to allow:
     - Azure Services
     - Two IP ranges

     .. code-block:: yaml

         policies:
             - name: add-sql-server-firewall
               resource: azure.sqlserver
               actions:
                 - type: set-firewall-rules
                   bypass-rules:
                       - AzureServices
                   ip-rules:
                       - 11.12.13.0/16
                       - 21.22.23.24
     """

    schema = type_schema(
        'set-firewall-rules',
        rinherit=SetFirewallAction.schema,
        **{
            'bypass-rules': {'type': 'array', 'items': {
                'enum': ['AzureServices']}},
            'prefix': {'type': 'string', 'maxLength': 91}  # 128 symbols less guid and dash
        }
    )

    def __init__(self, data, manager=None):
        super(SqlSetFirewallAction, self).__init__(data, manager)
        self.log = log
        self.prefix = data.get('prefix', 'c7n')

    def _process_resource(self, resource):
        # Get existing rules
        old_ip_rules = list(self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name']))
        old_ip_space = [IPRange(r.start_ip_address, r.end_ip_address) for r in old_ip_rules]

        # Build new rules
        new_ip_rules = self._build_ip_rules(old_ip_space, self.data.get('ip-rules', []))

        # Normalize data types into IPNetwork and IPRange
        new_ip_space = self._normalize_rules(new_ip_rules)

        # Build bypass rules
        # SQL uses a 0.0.0.0 rule to track "Azure Services" bypass
        old_bypass = []
        if AZURE_SERVICES in old_ip_space:
            old_bypass.append('AzureServices')

        new_bypass = self.data.get('bypass-rules', old_bypass)
        if 'AzureServices' in new_bypass and AZURE_SERVICES not in new_ip_space:
            new_ip_space.append(AZURE_SERVICES)

        # Update ARM resources
        to_remove_ip_space = set(old_ip_space).difference(new_ip_space)
        for r in to_remove_ip_space:
            remove = next(i for i in old_ip_rules
                          if i.start_ip_address == str(IPAddress(r.first)) and
                          i.end_ip_address == str(IPAddress(r.last)))
            self.client.firewall_rules.delete(
                resource['resourceGroup'],
                resource['name'],
                remove.name
            )

        to_add_ip_space = set(new_ip_space).difference(old_ip_space)
        for r in to_add_ip_space:
            first = IPAddress(r.first)
            last = IPAddress(r.last)
            self.client.firewall_rules.create_or_update(
                resource['resourceGroup'],
                resource['name'],
                self._generate_rule_name(r),
                str(first),
                str(last)
            )

        return 'Added {} rules, removed {} rules.'.format(
            len(to_add_ip_space), len(to_remove_ip_space))

    def _normalize_rules(self, new_ip_rules):
        new_ip_space = []
        for rule in new_ip_rules:
            if '-' in rule:
                parts = rule.split('-')
                new_ip_space.append(IPRange(parts[0], parts[1]))
            else:
                net = IPNetwork(rule)
                new_ip_space.append(IPRange(net.first, net.last))
        return new_ip_space

    def _generate_rule_name(self, rule):
        if rule == AZURE_SERVICES:
            return 'AllowAllWindowsAzureIps'
        return self.prefix + "-" + str(uuid.uuid4())
