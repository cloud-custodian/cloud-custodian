# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import uuid
from c7n_azure.actions.firewall import SetFirewallAction
from c7n_azure.filters import FirewallRulesFilter, FirewallBypassFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ThreadHelper, StringUtils
from netaddr import IPRange, IPSet, IPNetwork, IPAddress

from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema
from c7n.filters import Filter
from c7n.filters.core import ValueFilter, ListItemFilter

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


@SqlServer.filter_registry.register('transparent-data-encryption')
class TransparentDataEncryptionFilter(Filter):
    """
    Filter by the current Transparent Data Encryption
    configuration for this server.

    :example:

    Find SQL Server with TDE details

    .. code-block:: yaml

        policies:
          - name: sql-server-tde
            resource: azure.sql-server
            filters:
              - type: transparent-data-encryption
                key_type: CustomerManaged

    """

    schema = type_schema(
        'transparent-data-encryption',
        required=['type', 'key_type'],
        **{
            'key_type': {'type': 'string', 'enum': ['ServiceManaged', 'CustomerManaged']}
        }
    )

    log = logging.getLogger('custodian.azure.sqlserver.transparent-data-encryption-filter')

    def __init__(self, data, manager=None):
        super(TransparentDataEncryptionFilter, self).__init__(data, manager)
        self.key_type = self.data['key_type']

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

            encryption_protector = client.encryption_protectors.get(
                resource['resourceGroup'],
                resource['name'],
                "current")

            resource['properties']['transparentDataEncryption'] = \
                encryption_protector.serialize(True).get('properties', {})

            if self.key_type == 'CustomerManaged':
                encryption_type = 'AzureKeyVault'
            elif self.key_type == 'ServiceManaged':
                encryption_type = 'ServiceManaged'

            if StringUtils.equal(
                    resource['properties']['transparentDataEncryption'].get('serverKeyType'),
                    encryption_type):
                result.append(resource)

        return result


@SqlServer.filter_registry.register('failover-group')
class FailoverGroupFilter(ListItemFilter):
    schema = type_schema(
        "failover-group",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotate_items = True
    item_annotation_key = "c7n:FailoverGroups"

    def get_item_values(self, resource):
        groups = self.manager.get_client().failover_groups.list_by_server(
            resource_group_name=resource['resourceGroup'],
            server_name=resource['name']
        )
        return [g.serialize(True) for g in groups]


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
class VulnerabilityAssessmentFilter(ValueFilter):
    """
    Filter sql servers by whether they have recurring vulnerability scans
    enabled.

    :example:

    Find SQL servers without vulnerability assessments enabled (legacy)

    .. code-block:: yaml

        policies:
          - name: sql-server-no-va
            resource: azure.sql-server
            filters:
              - type: vulnerability-assessment
                enabled: false

    :example:

    Find SQL Servers where vulnerability assessments are not being sent to a
    required email

    .. code-block:: yaml

        policies:
          - name: sql-server-no-email
            resource: azure.sql-server
            filters:
              - type: vulnerability-assessment
                key: recurringScans.emails[?@ == `required@ops.domain`]
                value: empty

    When using the above value filter form, the data takes the following shape:

    .. code-block:: json

        "storageContainerPath": "https://testznubm7c1.blob.core.windows.net/testznubm7c1/",
        "recurringScans": {
            "isEnabled": true,
            "emailSubscriptionAdmins": false,
            "emails": [
                "ops@fake.email",
                "admins@fake.email"
            ]
        }

    """

    schema = type_schema(
        'vulnerability-assessment',
        rinherit=ValueFilter.schema,
        enabled=dict(type='boolean')
    )

    log = logging.getLogger('custodian.azure.sqldatabase.vulnerability-assessment-filter')

    def validate(self):
        # only allow legacy behavior or new ValueFilter behavior, not both
        # when in "legacy" mode the only entries should be "type" (required by schema) and
        # "enabled" (required by is_legacy)
        if self.is_legacy:
            if len(self.data) > 2:
                raise PolicyValidationError(
                    "When using 'enabled', ValueFilter properties are not allowed")
        # only validate value filter when not in "legacy" mode
        else:
            super(VulnerabilityAssessmentFilter, self).validate()

    def __init__(self, data, manager=None):
        super(VulnerabilityAssessmentFilter, self).__init__(data, manager)

        self.enabled = self.data.get('enabled')
        # track if we are using the legacy behavior
        self.is_legacy = 'enabled' in self.data
        # location on the resource object to store the VA properties
        self.key = 'c7n:vulnerability_assessment'

    def process(self, resources, event=None):
        # process the servers in parallel, updating them in place
        # with the VA assesment properties
        _, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )

        if exceptions:
            raise exceptions[0]

        return super(VulnerabilityAssessmentFilter, self).process(resources, event)

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client()
        for resource in resources:
            if self.key not in resource:
                va = list(client.server_vulnerability_assessments.list_by_server(
                    resource['resourceGroup'],
                    resource['name']))

                if va:
                    # there can only be a single instance
                    resource[self.key] = va[0].serialize(True).get('properties', {})
                else:
                    resource[self.key] = {}

    def __call__(self, resource):
        recurring_scan_enabled = resource[self.key] \
            .get('recurringScans', {}) \
            .get('isEnabled', False)

        # Apply filter based on legacy behavior which only verifies recurringScans.isEnabled
        if self.is_legacy:
            return recurring_scan_enabled == self.enabled
        # otherwise process the VA info using ValueFilter logic for full flexibility
        else:
            return super(VulnerabilityAssessmentFilter, self).__call__(resource[self.key])


@SqlServer.filter_registry.register('advanced-threat-protection')
class AdvancedThreatProtectionFilter(Filter):
    """
    Filter sql servers by their advanced protection state

    :example:

    Find SQL servers without vulnerability assessments enabled

    .. code-block:: yaml

        policies:
          - name: sql-server-no-atp
            resource: azure.sql-server
            filters:
              - type: advanced-threat-protection
                enabled: false

    """

    schema = type_schema(
        'advanced-threat-protection',
        required=['type', 'enabled'],
        **{
            'enabled': {"type": "boolean"},
        }
    )

    cache_key = 'c7n:advanced-threat-protection'

    def process(self, resources, event=None):
        # process the servers in parallel, updating them in place
        # with the VA assesment properties
        filtered, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )

        if exceptions:
            raise exceptions[0]

        return filtered

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client()
        filtered = []
        for resource in resources:
            if self.cache_key not in resource:
                atp = list(client.server_advanced_threat_protection_settings.list_by_server(
                    resource['resourceGroup'],
                    resource['name']))

                if atp:
                    # there can only be a single instance
                    resource[self.cache_key] = atp[0].serialize(True).get('properties', {})
                else:
                    resource[self.cache_key] = {}

            is_enabled = resource[self.cache_key].get('state') == 'Enabled'

            if is_enabled == self.data['enabled']:
                filtered.append(resource)

        return filtered


@SqlServer.filter_registry.register('firewall-rules')
class SqlServerFirewallRulesFilter(FirewallRulesFilter):
    def _query_rules(self, resource):
        query = self.client.firewall_rules.list_by_server(
            resource['resourceGroup'],
            resource['name'])

        resource_rules = IPSet()

        for r in query:
            rule = IPRange(r.start_ip_address, r.end_ip_address)
            if rule == AZURE_SERVICES and not self.data.get('include-azure-services', False):
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


@SqlServer.filter_registry.register('auditing')
class AuditingFilter(ValueFilter):
    """
    Filter by the current auditing
    policy for this sql server.

    :example:

    Find SQL servers with auditing disabled

    .. code-block:: yaml

        policies:
          - name: sql-database-no-auditing
            resource: azure.sql-server
            filters:
              - type: auditing
                enabled: false

    """

    cache_key = 'c7n:auditing-settings'

    schema = type_schema(
        'auditing',
        rinherit=ValueFilter.schema,
        enabled=dict(type='boolean')
    )

    log = logging.getLogger('custodian.azure.sqlserver.auditing-filter')

    def __init__(self, data, manager=None):
        super().__init__(data, manager)

        self.enabled = self.data.get('enabled')
        # track if we are using the legacy behavior
        self.is_legacy = 'enabled' in self.data

    def validate(self):
        # only allow legacy behavior or new ValueFilter behavior, not both
        # when in "legacy" mode the only entries should be "type" (required by schema) and
        # "enabled" (required by is_legacy)
        if self.is_legacy:
            if len(self.data) > 2:
                raise PolicyValidationError(
                    "When using 'enabled', ValueFilter properties are not allowed")
        # only validate value filter when not in "legacy" mode
        else:
            super().validate()

    def process(self, resources, event=None):
        _, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )

        if exceptions:
            raise exceptions[0]

        return super().process(resources, event)

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client()
        for resource in resources:
            if self.cache_key not in resource['properties']:
                auditing_settings = client.server_blob_auditing_policies.get(
                    resource['resourceGroup'],
                    resource['name'])

                resource['properties'][self.cache_key] = \
                    auditing_settings.serialize(True).get('properties', {})

    def __call__(self, resource):
        auditing_enabled = resource['properties'][self.cache_key].get('state') == 'Enabled'

        # Apply filter based on legacy behavior which only checks against enablement
        if self.is_legacy:
            return auditing_enabled == self.enabled
        # otherwise process the auditing settings using ValueFilter logic for full flexibility
        else:
            return super().__call__(resource['properties'][self.cache_key])


@SqlServer.filter_registry.register('security-alert-policies')
class SecurityAlertPoliciesFilter(ListItemFilter):
    """
    Filters sql servers by security alert policies

    .. code-block:: yaml

        policies:
          - name: sql-server-filter
            resource: azure.sql-server
            filters:
              - type: security-alert-policies
                attrs: []

    """
    schema = type_schema(
        "security-alert-policies",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotate_items = True
    item_annotation_key = "c7n:SecurityAlertPolicies"

    def get_item_values(self, resource):
        client = self.manager.get_client()
        policies = client.server_security_alert_policies.list_by_server(
            resource['resourceGroup'],
            resource['name']
        )  # always only one item
        return [p.serialize(True) for p in policies]


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


@SqlServer.filter_registry.register('auditing-policies')
class SqlServerAuditingSettingsFilter(ListItemFilter):
    """
    Filter sql servers by auditing policies.

    :example:

    Find SQL servers where there are auditing policies with retention less than a week

    .. code-block:: yaml

        policies:
          - name: auditing-policy-retention-less-a-week
            resource: azure.sql-server
            filters:
              - type: auditing-policies
                attrs:
                  - type: value
                    key: retentionDays
                    value: 7
                    op: less-than


    """
    schema = type_schema(
        'auditing-policies',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    annotation_key = 'c7n:auditing-settings-list'
    annotate_items = True

    def process(self, resources, event=None):
        _, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resources,
            executor_factory=self.executor_factory,
            log=log
        )

        if exceptions:
            raise exceptions[0]  # pragma: no cover
        return super().process(resources, event)

    def _process_resources(self, resources, event=None):
        cl = self.manager.get_client()
        for res in resources:
            properties = res.setdefault('properties', {})
            if self.annotation_key in properties:
                continue  # pragma: no cover
            settings = cl.server_blob_auditing_policies.list_by_server(
                resource_group_name=res['resourceGroup'],
                server_name=res['name']
            )
            properties[self.annotation_key] = [
                s.serialize(True).get('properties', {}) for s in settings
            ]

    def get_item_values(self, resource):
        return resource['properties'].get(self.annotation_key, [])
