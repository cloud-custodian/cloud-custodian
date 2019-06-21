from c7n_azure.utils import ResourceIdParser

from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from azure.mgmt.resource.locks import ManagementLockClient
from azure.mgmt.resource.locks.models import ManagementLockObject


class LockAction(AzureBaseAction):

    """
      Perform lock operation on any ARM resource. Can be used with
      generic resource type `armresource` or on any other more specific
      ARM resource type supported by Cloud Custodian.

      Lock can be of 2 types: ReadOnly and CanNotDelete. Lock type is required.

      To create or delete management locks, you must have proper access.
      See [Who can create or delete locks](https://docs.microsoft.com/en-us/azure/
      azure-resource-manager/resource-group-lock-resources#who-can-create-or-delete-locks)

      Example of the policy that adds ReadOnly lock to all keyvaults:

     .. code-block:: yaml

       policies:
          - name: lock-keyvaults
            resource: azure.keyvault
            actions:
              - type: lock
                lock-type: ReadOnly
     """

    schema = type_schema(
        'lock',
        required=['lock-type'],
        **{
            'lock-type': {'type': 'string'}
        }
    )

    def __init__(self, data=None, manager=None, log_dir=None):
        super(LockAction, self).__init__(data, manager, log_dir)
        self.method = 'POST'
        self.lock_type = self.data['lock-type']

    def _process_resource(self, resource):
        s = self.manager.get_session()
        client = ManagementLockClient(s.get_credentials(), s.subscription_id)

        if resource.get('resourceGroup') is None:
            client.management_locks.create_or_update_at_resource_group_level(
                resource['name'],
                'lock_' + resource['name'] + '_' + self.lock_type,
                ManagementLockObject(level=self.lock_type)
            )
        else:
            client.management_locks.create_or_update_at_resource_level(
                resource['resourceGroup'],
                ResourceIdParser.get_namespace(resource['id']),
                ResourceIdParser.get_resource_name(resource.get('c7n:parent-id')) or '',
                ResourceIdParser.get_resource_type(resource['id']),
                resource['name'],
                'lock_' + resource['name'] + '_' + self.lock_type,
                ManagementLockObject(level=self.lock_type)
            )
