.. _azure_vnet:

Virtual Networks
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `VirtualNetwork <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2018_02_01.models.virtualnetwork?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will find all Virtual Networks that do not have DDOS protection enabled.

.. code-block:: yaml

    policies:
      - name: find-vnets-ddos-protection-disabled
        resource: azure.vnet
        filters:
          - type: value
            key: properties.enableDdosProtection
            op: equal
            value: False
