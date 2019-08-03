.. _azure_storage:

Storage
=======

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `StorageAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.storage.v2018_02_01.models.storageaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Storage Account Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftstoragestorageaccounts/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

- ``firewall-rules`` Firewall Rules Filter
    Filter based on firewall rules. Rules can be specified as x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.

    - `include`: the list of IP ranges or CIDR that firewall rules must include. The list must be a subset of the exact rules as is, the ranges will not be combined.
    - `equal`: the list of IP ranges or CIDR that firewall rules must match exactly.

  .. c7n-schema:: azure.storage.filters.firewall-rules

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

- ``set-network-rules`` Set network (firewall) rules.
    - `default-action`: Required. Can be either Allow or Deny. 
    - `bypass`: Optional. List of services that are allowed to bypass the rules. Any combination of AzureServices, 
       Logging and Metrics, e.g. [Logging, Metrics]. If not specified the property is not changed.
    - `ip-rules`: Optional. List of allowed ip-s or addresses. Specify empty list [] to remove all items.
      - `ip-address-or-range`: Ip address or range that is allowed.
    - `virtual-network-rules`: Optional. List of allowed virtual networks. Specify empty list [] to remove all items.
      - `virtual-network-resource-id`: Azure id of a subnet of a virtual network.

  .. c7n-schema:: azure.storage.actions.set-network-rules


Example Policies
----------------
- :ref:`azure_examples_add_firewall_rules_to_storage`

