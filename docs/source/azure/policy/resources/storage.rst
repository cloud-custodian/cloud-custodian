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
- Firewall Rules Filter (see :ref:`azure_filters`)

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

This set of policies will mark all storage accounts for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-storage-for-deletion
        resource: azure.storage
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
      - name: delete-test-storage
        resource: azure.storage
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all Storage Accounts with 100 or less transactions over the 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-storage-dropping-messages
        resource: azure.storage
        filters:
          - type: metric
            metric: Transactions
            op: le
            aggregation: total
            threshold: 100
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Inactive Storage Account
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
