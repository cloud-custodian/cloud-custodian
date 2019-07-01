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

from azure.graphrbac import GraphRbacManagementClient
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.filters import FirewallRulesFilter
from c7n_azure.provider import resources
from c7n_azure.session import Session

from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.utils import GraphHelper

from c7n_azure.resources.arm import ArmResourceManager

import logging

from netaddr import IPSet

log = logging.getLogger('custodian.azure.keyvault')


@resources.register('keyvault')
class KeyVault(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)
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
            client = self.manager.get_client()
            vault = client.vaults.get(resource['resourceGroup'], resource['name'])
            resource['properties'] = vault.properties.serialize()

        if 'networkAcls' not in resource['properties']:
            return []

        ip_rules = resource['properties']['networkAcls']['ipRules']

        resource_rules = IPSet([r['value'] for r in ip_rules])
        return resource_rules


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
                lower_user_perm = set([x.lower() for x in user_permissions[v]])
                lower_perm = set([x.lower() for x in permissions[v]])
                if lower_user_perm.difference(lower_perm):
                    # If user has more permissions than allowed -- Failed
                    return False

        return True

    def _enhance_policies(self, access_policies):
        if not access_policies:
            return access_policies

        if self.graph_client is None:
            s = Session(resource='https://graph.windows.net')
            self.graph_client = GraphRbacManagementClient(s.get_credentials(), s.get_tenant_id())

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
                properties=access_policies
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
