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
from c7n_azure.provider import resources
from c7n_azure.session import Session

from c7n.filters import ValueFilter
from c7n.utils import type_schema
from c7n_azure.utils import GraphHelper

from c7n_azure.resources.arm import ArmResourceManager


@resources.register('keyvault')
class KeyVault(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)


@KeyVault.filter_registry.register('whitelist')
class WhiteListFilter(ValueFilter):
    schema = type_schema('whitelist', rinherit=ValueFilter.schema)
    graph_client = None

    def __init__(self, data, manager=None):
        super(WhiteListFilter, self).__init__(data, manager)
        self.op = 'difference'

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
            # Enhance access policies with display_name, object_type and principal_name
            i['accessPolicies'] = self.enhance_policies(access_policies)
        return super(WhiteListFilter, self).__call__(i)

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
