.. _azure_resourcegroup:

Resource Groups
===============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `ResourceGroup <https://docs.microsoft.com/en-us/python/api/azure.mgmt.resource.resources.v2017_05_10.models.resourcegroup?view=azure-python>`_
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
