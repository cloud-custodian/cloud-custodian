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

This policy will find all public IP addresses under DDoS attack over the last 72 hours

.. code-block:: yaml

    policies:
      - name: publicip-dropping-packets
        resource: azure.publicip
        filters:
          - type: metric
            metric: IfUnderDDoSAttack
            op: gt
            aggregation: maximum
            threshold: 0
            timeframe: 72

:ref:`This policy <azure_orphanresources-publicip>` will find all public IP addresses that are not being attached to Network Interface