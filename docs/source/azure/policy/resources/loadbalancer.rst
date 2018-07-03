.. _azure_loadbalancer:

Load Balancer
=============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `LoadBalancer <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2017_11_01.models.loadbalancer?view=azure-python>`_
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
