from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction


class DeleteAction(AzureBaseAction):
    schema = type_schema('delete')

    def _prepare_processing(self,):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        self.client.resources.delete_by_id(resource['id'],
                                      self.session.resource_api_version(resource['id']))
