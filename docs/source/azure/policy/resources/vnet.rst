.. _azure_vnet:

Virtual Networks
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `VirtualNetwork <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2018_02_01.models.virtualnetwork?view=azure-python>`_
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
