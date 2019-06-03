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

- ``firewall-rules`` Firewall Rules Filter (see :ref:`azure_filters`)

  .. c7n-schema:: StorageFirewallRulesFilter
       :module: c7n_azure.resources.storage

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

  .. c7n-schema:: StorageSetNetworkRulesAction
       :module: c7n_azure.resources.storage

Example Policies
----------------
- :ref:`azure_examples_add_firewall_rules_to_storage`

