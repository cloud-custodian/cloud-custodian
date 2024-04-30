# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n.filters.core import type_schema
from c7n_azure.utils import ResourceIdParser
from msrestazure.tools import parse_resource_id


@resources.register('storage-container')
class StorageContainer(ChildArmResourceManager):
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

    def get_resources(self, resource_ids):
        client = self.get_client()
        data = [
            self.get_storage_container(rid, client)
            for rid in resource_ids
        ]
        return self.augment([r.serialize(True) for r in data])

    def get_storage_container(self, resource_id, client):
        parsed = parse_resource_id(resource_id)
        return client.blob_containers.get(parsed.get('resource_group'),
                                          parsed.get('name'),             # Account name
                                          parsed.get('resource_name'))    # Container name


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

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        resource_group = ResourceIdParser.get_resource_group(resource['id'])
        account_name = ResourceIdParser.get_resource_name(resource['c7n:parent-id'])
        blob_container = self.client.blob_containers.get(resource_group,
            account_name,
            resource['name'],
        )
        blob_container.public_access = self.data['value']
        self.client.blob_containers.update(
            resource_group,
            account_name,
            resource['name'],
            blob_container
        )
