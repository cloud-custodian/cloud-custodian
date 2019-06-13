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

  .. c7n-schema:: azure.appserviceplan.filters.onhour

- ``offhour``

  .. c7n-schema:: azure.appserviceplan.filters.offhour


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

- ``resize-plan``
  Resize an app service plan by changing either the SKU or the number of instances.

  .. c7n-schema:: azure.appserviceplan.actions.resize-plan


Example Policies
----------------
- :ref:`azure_examples_resize_app_service_plan`
