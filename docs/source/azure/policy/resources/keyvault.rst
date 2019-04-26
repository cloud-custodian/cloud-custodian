.. _azure_keyvault:

Key Vault
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Key Vault Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftkeyvaultvaults/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- Whitelist filter - Filter on whitelist of Service Principals allowed to have a KeyVault access or Service Principals with specified access permissions
    - You can use `objectId`, `displayName`, `principalName` for the key
    - You can specify allowed set of permissions for keys, secrets and certificates (case insensitive)
    - Keys permissions: `Get`, `Create`, `Delete`, `List`, `Update`, `Import`, `Backup`, `Restore`, `Recover`, `Decrypt`, `UnwrapKey`, `Encrypt`, `WrapKey`, `Verify`, `Sign`, `Purge`
    - Secret permissions: `Get`, `List`, `Set`, `Delete`, `Backup`, `Restore`, `Recover`, `Purge`
    - Certificate permissions: `Get`, `List`, `Delete`, `Create`, `Import`, `Update`, `ManageContacts`, `GetIssuers`, `ListIssuers`, `SetIssuers`, `DeleteIssuers`, `ManageIssuers`, `Recover`, `Backup`, `Restore`, `Purge`
    - Note: if you use `displayName` or `principalName`, you need to use azure cli authentication

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

- ``update-access-policy`` - Add or Replace access policies from key vaults under a provided principal object id
    - operation: `add`, `append`
        - `add`: adds or appends permission
        - `replace`: replaces existing access policy
    - tenant-id: The tenant id of the object id and is used for authenticating with keyvault
    - object-id: The object id of the user or service principal. This can be retrieved through azure cli or azure portal
    - Keys permissions: `Get`, `Create`, `Delete`, `List`, `Update`, `Import`, `Backup`, `Restore`, `Recover`, `Decrypt`, `UnwrapKey`, `Encrypt`, `WrapKey`, `Verify`, `Sign`, `Purge`
    - Secret permissions: `Get`, `List`, `Set`, `Delete`, `Backup`, `Restore`, `Recover`, `Purge`
    - Certificate permissions: `Get`, `List`, `Delete`, `Create`, `Import`, `Update`, `ManageContacts`, `GetIssuers`, `ListIssuers`, `SetIssuers`, `DeleteIssuers`, `ManageIssuers`, `Recover`, `Backup`, `Restore`, `Purge`

  .. c7n-schema:: KeyVaultUpdateAccessPolicyAction
       :module: c7n_azure.resources.key_vault

Example Policies
----------------

This set of policies will mark all Key Vaults for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-keyvaults-for-deletion
        resource: azure.keyvault
        filters:
          - type: value
            key: name
            op: in
            value_type: normalize
            value: test
         actions:
          - type: mark-for-op
            op: delete
            days: 7
      - name: delete-test-keyvaults
        resource: azure.keyvault
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all KeyVaults with 10 or less API Hits over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-inactive-keyvaults
        resource: azure.keyvault
        filters:
          - type: metric
            metric: ServiceApiHit
            op: ge
            aggregation: total
            threshold: 10
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Inactive Key Vault
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename

This policy will find all KeyVaults with an access of Service Principals not in the white list that exceed read-only access

.. code-block:: yaml

    policies:
        - name: policy
          description:
            Ensure only authorized people have an access
          resource: azure.keyvault
          filters:
            - not:
              - type: whitelist
                key: principalName
                users:
                  - account1@sample.com
                  - account2@sample.com
                permissions:
                  keys:
                    - get
                  secrets:
                    - get
                  certificates:
                    - get

This policy will find all KeyVaults and add get and list permissions for keys.

.. code-block:: yaml

    policies:
        - name: policy
          description:
            Add get and list permissions to keys access policy
          resource: azure.keyvault
          actions:
            - type: update-access-policy
              operation: add
              access-policies:
                - tenant-id: 00000000-0000-0000-0000-000000000000
                  object-id: 11111111-1111-1111-1111-111111111111
                  permissions:
                    keys:
                      - get
                      - list