.. _azure_vmss:

Virtual Machine Scale Set
=========================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `VirtualMachineScaleSet <https://docs.microsoft.com/en-us/python/api/azure.mgmt.compute.v2017_12_01.models.virtualmachinescaleset?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will find all VM Scale Sets that are set to overprovision.

.. code-block:: yaml

    policies:
      - name: find-vmss-overprovision-true
        resource: azure.vmss
        filters:
          - type: value
            key: properties.overprovision
            op: equal
            value: True