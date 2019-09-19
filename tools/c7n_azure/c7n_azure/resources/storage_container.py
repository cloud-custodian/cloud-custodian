# Copyright 2019 Microsoft Corporation
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

from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo, ChildResourceManager
from c7n_azure.actions.base import AzureBaseAction
from c7n.filters.core import type_schema
from c7n_azure.utils import ResourceIdParser


@resources.register('storage-container')
class StorageContainer(ChildResourceManager):
    """Storage Container Resource

    :example:

    Finds all containers with public access enabled

    .. code-block:: yaml

        policies:
          - name: storage-container-public
            description: |
              Find all containers with public access enabled
            resource: azure.storage-container
            filters:
              - type: value
                key: properties.publicAccess
                op: not-equal
                value: None   # Possible values: Blob, Container, None
    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Storage']
        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('blob_containers', 'list', None)
        parent_manager_name = 'storage'
        diagnostic_settings_enabled = False
        resource_type = 'Microsoft.Storage/storageAccounts/blobServices/containers'
        enable_tag_operations = False
        raise_on_exception = False
        default_report_fields = (
            'name',
            'properties.publicAccess',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'account_name': parent_resource['name']}


@StorageContainer.action_registry.register('set-public-access')
class StorageContainerSetPublicAccessAction(AzureBaseAction):
    """Action that updates the access level setting on Storage Containers.
    Programmatically, this will be seen by updating the Public Access setting

    :example:

       Finds all Blob Storage Containers that are not private and sets them to private

    .. code-block:: yaml

        policies:
            - name: set-non-production-accounts-private
              resource: azure.storage-container
              filters:
                - type: value
                  key: properties.publicAccess
                  op: not-equal
                  value: None
              actions:
                - type: set-public-access
                  value: None
    """
    schema = type_schema(
        'set-public-access',
        required=['value'],
        **{
            'value': {'enum': ['Container', 'Blob', 'None']}
        }
    )

    schema_alias = True

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        resource_group = ResourceIdParser.get_resource_group(resource['id'])
        account_name = ResourceIdParser.get_resource_name(resource['c7n:parent-id'])

        self.client.blob_containers.update(
            resource_group,
            account_name,
            resource['name'],
            public_access=self.data['value']
        )
