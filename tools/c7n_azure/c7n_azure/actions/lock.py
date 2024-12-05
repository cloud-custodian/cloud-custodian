# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.resource.locks.models import ManagementLockObject
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.utils import is_resource_group

from c7n.utils import type_schema


class LockAction(AzureBaseAction):

    """
    Perform lock operation on any ARM resource. Can be used with
    generic resource type `armresource` or on any other more specific
    ARM resource type supported by Cloud Custodian.

    Lock can be of 2 types: ReadOnly and CanNotDelete. Lock type is required.

    To create or delete management locks, you must have proper access.
    See `Who can create or delete locks <https://docs.microsoft.com/en-us/azure/
    azure-resource-manager/resource-group-lock-resources#who-can-create-or-delete-locks>`_

    :example:

    Add ReadOnly lock to all keyvaults:

    .. code-block:: yaml

       policies:
          - name: lock-keyvaults
            resource: azure.keyvault
            actions:
              - type: lock
                lock-type: ReadOnly

    :example:

    Add CanNotDelete lock to sqldatabases tagged env:production

    .. code-block:: yaml

       policies:
          - name: lock-production-sqldatabase
            resource: azure.sqldatabase
            filters:
              - type: value
                key: tags.env
                value: production
            actions:
              - type: lock
                lock-type: CanNotDelete
                lock-name: productionLock
                lock-notes: Locking all production SQL databases via Cloud Custodian

     """

    schema = type_schema(
        'lock',
        required=['lock-type'],
        **{
            'lock-type': {'enum': ['ReadOnly', 'CanNotDelete']},
            'lock-name': {'type': 'string', 'minLength': 1, 'maxLength': 260},
            'lock-notes': {'type': 'string', 'minLength': 1, 'maxLength': 512}
        }
    )

    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(LockAction, self).__init__(data, manager, log_dir)
        self.lock_type = self.data['lock-type']

    def _prepare_processing(self):
        self.client = self.manager.get_client('azure.mgmt.resource.locks.ManagementLockClient')

    def _process_resource(self, resource):
        lock_name = self._get_lock_name(resource)
        lock_notes = self._get_lock_notes(resource)

        if is_resource_group(resource):
            self.client.management_locks.create_or_update_at_resource_group_level(
                resource['name'],
                lock_name,
                ManagementLockObject(level=self.lock_type, notes=lock_notes)
            )
        else:
            self.client.management_locks.create_or_update_by_scope(
                resource['id'],
                lock_name,
                ManagementLockObject(level=self.lock_type, notes=lock_notes)
            )

        return {"locked": self.lock_type}

    def _get_lock_name(self, resource):
        return self.data.get('lock-name', "c7n-policy-{}".format(self.manager.data['name']))

    def _get_lock_notes(self, resource):
        return self.data.get('lock-notes')
