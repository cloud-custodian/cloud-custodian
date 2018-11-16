.. _azure_appserviceplan:

App Service Plan
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
    - Model: `AppServicePlan <https://docs.microsoft.com/en-us/python/api/azure.mgmt.web.models.AppServicePlan?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

- ``onhour``

  .. c7n-schema:: AzureOnHour
       :module: c7n_azure.filters

- ``offhour``

  .. c7n-schema:: AzureOffHour
       :module: c7n_azure.filters

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

- ``resize-plan``
  Resize an app service plan by changing either the SKU or the number of instances.

  .. c7n-schema:: ResizePlan
       :module: c7n_azure.resources.appserviceplan

Example Policies
----------------

This set of policies will mark all app services for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-appservice-for-deletion
        resource: azure.appserviceplan
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
      - name: delete-test-appservice
        resource: azure.appserviceplan
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete
