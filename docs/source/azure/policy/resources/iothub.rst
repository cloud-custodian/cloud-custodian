.. _azure_iothub:

Key Vault
=========

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Vault <https://docs.microsoft.com/en-us/python/api/azure.mgmt.keyvault.models.vault?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will mark all IoT Hubs for deletion in 3 days that have 'test' in name (ignore case)

.. code-block:: yaml

     policies:
       - name: delete-test-iothub
         resource: azure.iothub
         filters:
          - type:
         actions:
          - type:

This policy will

.. code-block:: yaml

     policies:
       - name:
         resource: azure.
         filters:
          - type:
         actions:
          - type:

This policy will

.. code-block:: yaml

     policies:
       - name:
         resource: azure.
         filters:
          - type:
         actions:
          - type:
