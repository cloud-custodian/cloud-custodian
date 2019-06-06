.. _azure_keyvaultkeys:

Key Vault Keys
==============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `Key Vault Key <https://docs.microsoft.com/en-us/python/api/azure-keyvault/azure.keyvault.v7_0.models.keyitem?view=azure-python>`_

- `keyvault` filter: filters keys from specified list of keyvaults.
    - `vaults`: array of strings, allowed key vault names

- `key-type` filter: Find all keys with specified types
    - `key-types`: array of types. 
        - Possible values: `RSA`, `RSA-HSM`, `EC`, `EC-HSM` 
    

Example Policies
----------------

This policy will find all Keys in `keyvault_test` and `keyvault_prod` KeyVaults

.. code-block:: yaml

    policies:
      - name: keyvault-keys
        description:
          List all keys from 'keyvault_test' and 'keyvault_prod' vaults
        resource: azure.keyvault-keys
        filters:
          - type: keyvault
            vaults:
              - keyvault_test
              - keyvault_prod


This policy will find all Keys in all KeyVaults that are older than 30 days

.. code-block:: yaml

    policies:
      - name: keyvault-keys
        description:
          List all keys that are older than 30 days
        resource: azure.keyvault-keys
        filters:
          - type: value
            key: attributes.created
            value_type: age
            op: gt
            value: 30


If your company wants to enforce usage of HSM-backed keys in the KeyVaults,
you can use this policy to find all Keys in all KeyVaults not backed by an HSM module.

.. code-block:: yaml

    policies:
      - name: keyvault-keys
        description:
          List all non-HSM keys
        resource: azure.keyvault-keys
        filters:
          - not:
             - type: key-type
               key-types:
                 - RSA-HSM, EC-HSM
