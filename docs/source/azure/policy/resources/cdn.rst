.. _azure_cdn:

CDN
===

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Profile <https://docs.microsoft.com/en-us/python/api/azure-mgmt-cdn/azure.mgmt.cdn.models.profile?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

Returns all CDNs with Standard_Verizon sku

.. code-block:: yaml

    policies:
      - name: standard-verizon
        resource: azure.cdnprofile
        filters:
          - type: value
            key: sku
            op: in
            value_type: normalize
            value: Standard_Verizon