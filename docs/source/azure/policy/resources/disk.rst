.. _azure_disk:

Disk
====

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Disk <https://docs.microsoft.com/en-us/python/api/azure.mgmt.compute.v2018_04_01.models.disk?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

Deletes all disks that are currently not being managed by a VM

.. code-block:: yaml

    policies:
      - name: orphaned-disks
        resource: azure.disk
        filters:
          - type: value
            key: managedBy
            value: null
        actions:
          - type: delete
