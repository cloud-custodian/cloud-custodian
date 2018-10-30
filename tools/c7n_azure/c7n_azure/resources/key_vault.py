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
from azure.keyvault import KeyVaultClient
from c7n_azure.provider import resources
from c7n_azure.session import Session
from c7n.filters import Filter
import logging
from c7n.utils import type_schema
from c7n_azure.utils import GraphHelper
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.constants import CONST_AZURE_KEYVAULT_BASEURL


log = logging.getLogger('custodian.azure.keyvault')


@resources.register('keyvault')
class KeyVault(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)


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
            # Enhance access policies with displayName, aadType and principalName
            i['accessPolicies'] = self.enhance_policies(access_policies)

        # Ensure each policy is
        #   - User is whitelisted
        #   - Permissions don't exceed allowed permissions
        for p in i['accessPolicies']:
            if p[self.key] not in self.users:
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

    def enhance_policies(self, access_policies):
        if self.graph_client is None:
            s = Session(resource='https://graph.windows.net')
            self.graph_client = GraphRbacManagementClient(s.get_credentials(), s.get_tenant_id())

        # Retrieve graph objects for all object_id
        object_ids = [p['objectId'] for p in access_policies]
        # GraphHelper.get_principal_dictionary returns empty AADObject if not found with graph
        # or if graph is not available.
        principal_dics = GraphHelper.get_principal_dictionary(self.graph_client, object_ids)

        for policy in access_policies:
            aad_object = principal_dics[policy['objectId']]
            policy['displayName'] = aad_object.display_name
            policy['aadType'] = aad_object.object_type
            policy['principalName'] = GraphHelper.get_principal_name(aad_object)

        return access_policies


@resources.register('keyvault-key')
class KeyVaultKey(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)

    def augment(self, resources):
        s = Session(resource='https://' + CONST_AZURE_KEYVAULT_BASEURL)
        self.keyvault_client = KeyVaultClient(s.get_credentials())
        r = []

        for ritem in resources:

            vault_url = 'https://' + ritem["name"] + "." + CONST_AZURE_KEYVAULT_BASEURL
            try:
                vkeys = self.keyvault_client.get_keys(vault_url)
                for vkey in vkeys:
                    keyname = vkey.kid.split("/")[-1:]
                    keyname = keyname[0]

                    r.append({'kid': vkey.kid,
                              'keyname': keyname,
                              'keyvault': {'id': ritem["id"],
                                           'name': ritem["name"],
                                           'location': ritem["location"],
                                           'tags': ritem["tags"]},
                              'enabled': vkey.attributes.enabled,
                              'created': vkey.attributes.created,
                              'updated': vkey.attributes.updated,
                              'tags': vkey.tags})

            except Exception as e:
                self.log.error(e.message + ' on keyvault: ' + ritem["id"])
                pass

        return r


@resources.register('keyvault-certificate')
class KeyVaultCert(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)

    def augment(self, resources):
        s = Session(resource='https://' + CONST_AZURE_KEYVAULT_BASEURL)
        self.keyvault_client = KeyVaultClient(s.get_credentials())
        r = []

        for ritem in resources:
            vault_url = 'https://' + ritem["name"] + "." + CONST_AZURE_KEYVAULT_BASEURL
            try:
                vcerts = self.keyvault_client.get_certificates(vault_url)
                for vcert in vcerts:
                    certname = vcert.id.split("/")[-1:]
                    certname = certname[0]

                    r.append({'id': vcert.id,
                              'certificate_name': certname,
                              'keyvault': {'id': ritem["id"],
                                           'name': ritem["name"],
                                           'location': ritem["location"],
                                           'tags': ritem["tags"]},
                              'enabled': vcert.attributes.enabled,
                              'created': vcert.attributes.created,
                              'updated': vcert.attributes.updated,
                              'tags': vcert.tags})

            except Exception as e:
                self.log.error(e.message + ' on keyvault: ' + ritem["id"])
                pass

        return r
