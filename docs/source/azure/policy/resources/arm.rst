.. _azure_armresource:

Network Interface
=================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `GenericResource <https://docs.microsoft.com/en-us/python/api/azure.mgmt.resource.resources.v2017_05_10.models.genericresource?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all ARM resources for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.


.. code-block:: yaml

    policies:
      - name: mark-test-armresources-for-deletion
        resource: azure.armresource
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
      - name: delete-test-armresources
        resource: azure.armresource
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete
