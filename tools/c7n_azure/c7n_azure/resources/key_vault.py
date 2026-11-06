# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging

from dateutil.parser import isoparse

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.constants import GRAPH_AUTH_ENDPOINT
from c7n_azure.filters import FirewallBypassFilter, FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.session import Session
from c7n_azure.utils import GraphHelper
from netaddr import IPSet

log = logging.getLogger('custodian.azure.keyvault')


@resources.register('keyvault')
class KeyVault(ArmResourceManager):

    """Key Vault Resource

    :example:

    This policy will find all KeyVaults with 10 or less API Hits over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: inactive-keyvaults
            resource: azure.keyvault
            filters:
              - type: metric
                metric: ServiceApiHit
                op: ge
                aggregation: total
                threshold: 10
                timeframe: 72

    :example:

    This policy will find all KeyVaults where Service Principals that
    have access permissions that exceed `read-only`.

    .. code-block:: yaml

        policies:
            - name: policy
              description:
                Ensure only authorized people have an access
              resource: azure.keyvault
              filters:
                - not:
                  - type: whitelist
                    key: principalName
                    users:
                      - account1@sample.com
                      - account2@sample.com
                    permissions:
                      keys:
                        - get
                      secrets:
                        - get
                      certificates:
                        - get

    :example:

    This policy will find all KeyVaults and add get and list permissions for keys.

    .. code-block:: yaml

        policies:
            - name: policy
              description:
                Add get and list permissions to keys access policy
              resource: azure.keyvault
              actions:
                - type: update-access-policy
                  operation: add
                  access-policies:
                    - tenant-id: 00000000-0000-0000-0000-000000000000
                      object-id: 11111111-1111-1111-1111-111111111111
                      permissions:
                        keys:
                          - get
                          - list

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Security']

        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list_by_subscription', None)
        resource_type = 'Microsoft.KeyVault/vaults'


@KeyVault.filter_registry.register('firewall-rules')
class KeyVaultFirewallRulesFilter(FirewallRulesFilter):

    def __init__(self, data, manager=None):
        super(KeyVaultFirewallRulesFilter, self).__init__(data, manager)
        self._log = log

    @property
    def log(self):
        return self._log

    def _query_rules(self, resource):

        if 'properties' not in resource:
            vault = self.client.vaults.get(resource['resourceGroup'], resource['name'])
            resource['properties'] = vault.properties.serialize()

        if 'networkAcls' not in resource['properties']:
            return IPSet(['0.0.0.0/0'])

        if resource['properties']['networkAcls']['defaultAction'] == 'Deny':
            ip_rules = resource['properties']['networkAcls']['ipRules']
            resource_rules = IPSet([r['value'] for r in ip_rules])
        else:
            resource_rules = IPSet(['0.0.0.0/0'])

        return resource_rules


@KeyVault.filter_registry.register('firewall-bypass')
class KeyVaultFirewallBypassFilter(FirewallBypassFilter):
    """
    Filters resources by the firewall bypass rules.

    :example:

    This policy will find all KeyVaults with enabled Azure Services bypass rules

    .. code-block:: yaml

        policies:
          - name: keyvault-bypass
            resource: azure.keyvault
            filters:
              - type: firewall-bypass
                mode: equal
                list:
                    - AzureServices
    """
    schema = FirewallBypassFilter.schema(['AzureServices'])

    def _query_bypass(self, resource):

        if 'properties' not in resource:
            vault = self.client.vaults.get(resource['resourceGroup'], resource['name'])
            resource['properties'] = vault.properties.serialize()

        # Remove spaces from the string for the comparision
        if 'networkAcls' not in resource['properties']:
            return []

        if resource['properties']['networkAcls']['defaultAction'] == 'Allow':
            return ['AzureServices']

        bypass_string = resource['properties']['networkAcls'].get('bypass', '').replace(' ', '')
        return list(filter(None, bypass_string.split(',')))


@KeyVault.filter_registry.register('whitelist')
class WhiteListFilter(Filter):
    schema = type_schema('whitelist', rinherit=None,
                         required=['key'],
                         key={'type': 'string'},
                         users={'type': 'array'},
                         permissions={
                             'certificates': {'type': 'array'},
                             'secrets': {'type': 'array'},
                             'keys': {'type': 'array'}})
    GRAPH_PROVIDED_KEYS = ['displayName', 'aadType', 'principalName']
    graph_client = None

    def __init__(self, data, manager=None):
        super(WhiteListFilter, self).__init__(data, manager)
        self.key = self.data['key']
        # If not specified, initialize with empty list or dictionary.
        self.users = self.data.get('users', [])
        self.permissions = self.data.get('permissions', {})

    def __call__(self, i):
        if 'accessPolicies' not in i:
            client = self.manager.get_client()
            vault = client.vaults.get(i['resourceGroup'], i['name'])
            # Retrieve access policies for the keyvaults
            access_policies = []
            for policy in vault.properties.access_policies:
                access_policies.append({
                    'tenantId': policy.tenant_id,
                    'objectId': policy.object_id,
                    'applicationId': policy.application_id,
                    'permissions': {
                        'keys': policy.permissions.keys,
                        'secrets': policy.permissions.secrets,
                        'certificates': policy.permissions.certificates
                    }
                })
            # Enhance access policies with displayName, aadType and
            # principalName if necessary
            if self.key in self.GRAPH_PROVIDED_KEYS:
                i['accessPolicies'] = self._enhance_policies(access_policies)

        # Ensure each policy is
        #   - User is whitelisted
        #   - Permissions don't exceed allowed permissions
        for p in i['accessPolicies']:
            if self.key not in p or p[self.key] not in self.users:
                if not self.compare_permissions(p['permissions'], self.permissions):
                    return False
        return True

    @staticmethod
    def compare_permissions(user_permissions, permissions):
        for v in user_permissions.keys():
            if user_permissions[v]:
                if v not in permissions.keys():
                    # If user_permissions is not empty, but allowed permissions is empty -- Failed.
                    return False
                # User lowercase to compare sets
                lower_user_perm = {x.lower() for x in user_permissions[v]}
                lower_perm = {x.lower() for x in permissions[v]}
                if lower_user_perm.difference(lower_perm):
                    # If user has more permissions than allowed -- Failed
                    return False

        return True

    def _enhance_policies(self, access_policies):
        if not access_policies:
            return access_policies

        if self.graph_client is None:
            s = Session(resource_endpoint_type=GRAPH_AUTH_ENDPOINT)
            self.graph_client = s.client('azure.graphrbac.GraphRbacManagementClient')

        # Retrieve graph objects for all object_id
        object_ids = [p['objectId'] for p in access_policies]
        # GraphHelper.get_principal_dictionary returns empty AADObject if not found with graph
        # or if graph is not available.
        principal_dics = GraphHelper.get_principal_dictionary(
            self.graph_client, object_ids, True)

        for policy in access_policies:
            aad_object = principal_dics[policy['objectId']]
            if aad_object.object_id:
                policy['displayName'] = aad_object.display_name
                policy['aadType'] = aad_object.object_type
                policy['principalName'] = GraphHelper.get_principal_name(aad_object)

        return access_policies


class KeyVaultPropertiesUpdateAction(AzureBaseAction):
    """Shared date handling for the ``update`` actions on Key Vault child resources.

    ``not_before`` and ``expires_on`` are checked when the policy is validated,
    then resolved once per run into ``self.not_before`` and ``self.expires_on``
    for ``_process_resource`` to send. An ``expires_in_days`` value, where the
    subclass schema allows it, sets the expiration relative to the run.
    """

    def validate(self):
        if 'expires_on' in self.data and 'expires_in_days' in self.data:
            raise PolicyValidationError(
                f"'expires_on' and 'expires_in_days' are mutually exclusive "
                f"on {self.manager.data}")
        for field in ('not_before', 'expires_on'):
            if field not in self.data:
                continue
            try:
                isoparse(self.data[field])
            except (TypeError, ValueError):
                raise PolicyValidationError(
                    f"'{field}' must be an ISO formatted date, "
                    f"got {self.data[field]!r} on {self.manager.data}")
        if self.data.get('not_before') and self.data.get('expires_on'):
            self._check_window(
                isoparse(self.data['not_before']),
                isoparse(self.data['expires_on']),
                PolicyValidationError)
        return self

    def _check_window(self, not_before, expires_on, error):
        # Naive datetimes are sent to Key Vault as UTC, so compare them as UTC.
        def as_utc(dt):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt

        if not_before and expires_on and as_utc(not_before) >= as_utc(expires_on):
            raise error(
                f"'not_before' ({not_before.isoformat()}) must be earlier than the "
                f"expiration ({expires_on.isoformat()}) on {self.manager.data}")

    def process(self, resources, event=None):
        # Imported here so the test harness's patch of utcnow takes effect.
        from c7n_azure.utils import utcnow

        # Resolved once per run, before resources are split across worker threads,
        # so every resource gets the same expiration.
        # isoparse accepts a trailing 'Z', which fromisoformat rejects before Python 3.11.
        self.not_before = self.expires_on = None
        if self.data.get('not_before'):
            self.not_before = isoparse(self.data['not_before'])

        if self.data.get('expires_on'):
            self.expires_on = isoparse(self.data['expires_on'])
        elif 'expires_in_days' in self.data:
            self.expires_on = utcnow() + datetime.timedelta(days=self.data['expires_in_days'])

        # An expires_in_days expiration is only known now; check before updating anything.
        self._check_window(self.not_before, self.expires_on, PolicyExecutionError)

        return super().process(resources, event)


@KeyVault.action_registry.register('update-access-policy')
class KeyVaultUpdateAccessPolicyAction(AzureBaseAction):
    """
        Adds Get and List key access policy to all keyvaults

            .. code-block:: yaml

              policies:
                - name: azure-keyvault-update-access-policies
                  resource: azure.keyvault
                  description: |
                    Add key get and list to all keyvault access policies
                  actions:
                   - type: update-access-policy
                     operation: add
                     access-policies:
                      - tenant-id: 00000000-0000-0000-0000-000000000000
                        object-id: 11111111-1111-1111-1111-111111111111
                        permissions:
                          keys:
                            - Get
                            - List

    """

    schema = type_schema('update-access-policy',
        required=['operation', 'access-policies'],
        operation={'type': 'string', 'enum': ['add', 'replace']},
        **{
            "access-policies": {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'tenant-id': {'type': 'string'},
                    'object-id': {'type': 'string'},
                    'permissions': {
                        'type': 'object',
                        'keys': {'type': 'array', 'items': {'type': 'string'}},
                        'secrets': {'type': 'array', 'items': {'type': 'string'}},
                        'certificates': {'type': 'array', 'items': {'type': 'string'}}
                    }
                }
            }
        })

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        operation = self.data.get('operation')
        access_policies = KeyVaultUpdateAccessPolicyAction._transform_access_policies(
            self.data.get('access-policies')
        )

        try:
            self.client.vaults.update_access_policy(
                resource_group_name=resource['resourceGroup'],
                vault_name=resource['name'],
                operation_kind=operation,
                parameters=dict(properties=access_policies),
            )
        except Exception as error:
            log.warning(error)

    @staticmethod
    def _transform_access_policies(access_policies):
        policies = [
            {"objectId": i['object-id'],
                "tenantId": i['tenant-id'],
                "permissions": i['permissions']} for i in access_policies]

        return {"accessPolicies": policies}
