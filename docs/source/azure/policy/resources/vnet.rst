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

This set of policies will mark all Virtual Networks for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-vnet-for-deletion
        resource: azure.vnet
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
      - name: delete-test-vnet
        resource: azure.vnet
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete
