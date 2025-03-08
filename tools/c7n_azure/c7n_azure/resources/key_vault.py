# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import logging
import inspect
from typing import get_args, _UnionGenericAlias

from c7n_azure.utils import type_to_jsonschema

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


@KeyVault.action_registry.register('update')
class KeyVaultUpdateAction(AzureBaseAction):
    """
    Update a keyvault

    To keep the tenant id the same, set it to "keep"
    To keep the sku settings the same, set it to {"current": True}

    For more information on Vault properties:

    https://learn.microsoft.com/en-us/python/api/azure-mgmt-keyvault/azure.mgmt.keyvault.v2023_07_01.models.vaultproperties?view=azure-python

    :example:

    .. code-block:: yaml

        policies:
            - name: keyvault-vault-disable-public-access
              resource: azure.keyvault
              filters:
                - name: test
              actions:
                - type: update
                  configuration:
                    tenant_id: keep
                    sku:
                      current: True
                    public_network_access: disabled
    """

    @staticmethod
    def generate_schema():
        from azure.mgmt.keyvault import KeyVaultManagementClient

        vault_properties = KeyVaultManagementClient.models().VaultProperties
        model_signature = inspect.signature(vault_properties)

        schema_dict = {}
        required = ["tenant_id", "sku"]

        for name, v in model_signature.parameters.items():

            if name == "kwargs":
                continue

            schema_dict.setdefault(name, {})

            if hasattr(v, "annotation"):
                if not isinstance(v.annotation, _UnionGenericAlias):
                    schema_dict[name] = type_to_jsonschema(v.annotation)
                    continue

                args = get_args(v.annotation)

                if type(None) not in args:
                    required.append(name)
                else:
                    args = list(args)
                    args.remove(type(None))

                if len(args) == 1:
                    schema_dict[name]['type'] = args[0]

                schema_dict[name] = type_to_jsonschema(args[0])

        return type_schema(
            "update",
            required=["configuration"],
            **{
                "configuration": {
                    "type": "object",
                    "properties": schema_dict,
                    "required": required
                }
            }
        )

    schema = generate_schema.__func__()  # python 3.9 compat

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def make_access_policy_entry(self, acp):
        permissions = self.client.models().Permissions(**acp["permissions"])
        return self.client.models().AccessPolicyEntry(
            tenant_id=acp["tenant_id"],
            object_id=acp["object_id"],
            application_id=acp["application_id"],
            permissions=permissions
        )

    def make_network_acl_rule_set(self, acl):
        ip_rules = [
            self.client.models().IPRule(**ip_rule)
            for ip_rule in acl.get("ip_rules", [])
        ]

        virtual_network_rules = [
            self.client.models().VirtualNetworkRule(**vn_rule)
            for vn_rule in acl.get("virtual_network_rules", [])
        ]

        return self.client.models().NetworkRuleSet(
            bypass=acl["bypass"],
            default_action=acl["default_action"],
            ip_rules=ip_rules,
            virtual_network_rules=virtual_network_rules,
        )

    def _process_resource(self, resource):
        props = copy.deepcopy(self.data["configuration"])

        if props['tenant_id'] == "keep":
            props["tenant_id"] = resource["properties"]["tenantId"]

        if props["sku"] == {"current": True}:
            props["sku"] = resource["properties"]["sku"]

        if props.get("access_policies"):
            props["access_policies"] = [
                self.make_access_policy_entry(p)
                for p in props["access_policies"]
            ]

        if props.get("network_acls"):
            props["network_acls"] = self.make_network_acl_rule_set(props["network_acls"])

        params = self.client.models().VaultCreateOrUpdateParameters(
            location=resource["location"],
            properties=self.client.models().VaultProperties(**props)
        )
        self.client.vaults.update(
            resource_group_name=resource["resourceGroup"],
            vault_name=resource["name"],
            parameters=params
        )
