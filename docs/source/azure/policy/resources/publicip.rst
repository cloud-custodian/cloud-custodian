.. _azure_publicip:

Public IP Address
=================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `PublicIPAddress <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2018_02_01.models.publicipaddress?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Public IP Address Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkpublicipaddresses/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all public IP addresses for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-public-ip-for-deletion
        resource: azure.publicip
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
      - name: delete-test-publicips
        resource: azure.publicip
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all public IP addresses under DDoS attack over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-publicip-dropping-packets
        resource: azure.publicip
        filters:
          - type: metric
            metric: IfUnderDDoSAttack
            op: gt
            aggregation: maximum
            threshold: 0
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 1
            subject: Public IP Under DDoS Attack
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
