from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction


class DeleteAction(AzureBaseAction):
    """
    Perform delete operation on any ARM resource. Can be used with
    generic resource type `armresource` or on any other more specific
    ARM resource type supported by Cloud Custodian.

    :example:
    This policy will delete any ARM resource with 'test' in the name

    .. code-block:: yaml

            policies:
              - name: delete-test-resources
                resource: azure.armresource
                description: |
                  Deletes any ARM resource with 'test' in the name
                filters:
                  - type: value
                    key: name
                    value: test
                    op: contains
                actions:
                 - type: delete

    :example:
    This policy will delete any Network Security Group  with 'test' in the name

    .. code-block:: yaml

            policies:
               - name: delete-test-nsg
                 description: |
                   Deletes any Network Security Group with 'test' in the name
                 resource: azure.networksecuritygroup
                 filters:
                   - type: value
                     key: name
                     value: test
                     op: contains
                 actions:
                  - type: delete

    """

    schema = type_schema('delete')
    schema_alias = True

    def _prepare_processing(self,):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        self.client.resources.delete_by_id(resource['id'],
                                      self.session.resource_api_version(resource['id']))
