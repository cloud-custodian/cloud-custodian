.. _azure_policyassignments:

Policy assignments
==================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `Profile <https://docs.microsoft.com/en-us/python/api/azure-mgmt-cdn/azure.mgmt.cdn.models.profile?view=azure-python>`_

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will find all policy assignments named 'test-assignment' and delete them.

.. code-block:: yaml

  policies:
    - name: remove-test-assignments
      resource: azure.policyassignments
      filters:
        - type: value
          key: properties.displayName
          value_type: normalize
          op: eq
          value: 'test-assignment'
      actions:
        - type: delete