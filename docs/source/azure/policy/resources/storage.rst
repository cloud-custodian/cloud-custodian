.. _azure_storage:

Storage
=======

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `StorageAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.storage.v2018_02_01.models.storageaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

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

This policy will

.. code-block:: yaml

     policies:
       - name:
         resource: azure.
         filters:
          - type:
         actions:
          - type:
