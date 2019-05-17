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
# limitations under the License.from c7n_azure.provider import resources

import logging

from azure.keyvault.key_vault_id import KeyVaultId

from c7n.filters import Filter
from c7n.utils import type_schema

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ThreadHelper, ResourceIdParser, generate_key_vault_url


log = logging.getLogger('custodian.azure.keyvault.keys')


@resources.register('keyvault-keys')
class KeyVaultKeys(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        resource = constants.RESOURCE_VAULT
        service = 'azure.keyvault'
        client = 'KeyVaultClient'
        enum_spec = (None, 'get_keys', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        @classmethod
        def extra_args(cls, parent_resource):
            return {'vault_base_url': generate_key_vault_url(parent_resource['name'])}


@KeyVaultKeys.filter_registry.register('keyvault')
class KeyVaultFilter(Filter):
    schema = type_schema(
        'keyvault',
        required=['vaults'],
        **{
            'vaults': {'type': 'array', 'items': {'type': 'string'}}
        }
    )

    def process(self, resources, event=None):
        parent_key = self.manager.resource_type.parent_key
        return [r for r in resources
                if ResourceIdParser.get_resource_name(r[parent_key]) in self.data['vaults']]


@KeyVaultKeys.filter_registry.register('key-type')
class KeyTypeFilter(Filter):
    schema = type_schema(
        'key-type',
        **{
            'key-types': {'type': 'array', 'items': {'enum': ['EC', 'EC-HSM', 'RSA', 'RSA-HSM']}}
        }
    )

    def process(self, resources, event=None):

        resources, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )
        return resources

    def _process_resource_set(self, resources, event):
        client = self.manager.get_client()

        matched = []
        for resource in resources:
            try:
                if 'c7n:kty' not in resource:
                    id = KeyVaultId.parse_key_id(resource['kid'])
                    key = client.get_key(id.vault, id.name, id.version)

                    resource['c7n:kty'] = key.key.kty.lower()

                if resource['c7n:kty'] in [t.lower() for t in self.data['key-types']]:
                    matched.append(resource)
            except Exception as error:
                log.warning(error)

        return matched
