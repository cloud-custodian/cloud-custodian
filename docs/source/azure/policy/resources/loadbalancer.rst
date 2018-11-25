.. _azure_loadbalancer:

Load Balancer
=============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `LoadBalancer <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2017_11_01.models.loadbalancer?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Load Balancer Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftnetworkloadbalancers/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- ``frontend-public-ip``
  Filters load balancers by the frontend public IP

  .. c7n-schema:: FrontEndIp
      :module: c7n_azure.resources.load_balancer

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will filter load balancers with an ipv6 frontend public IP

.. code-block:: yaml

     policies:
       - name: loadbalancer-with-ipv6-frontend
         resource: azure.loadbalancer
         filters:
            - type: frontend-public-ip
              key: properties.publicIPAddressVersion
              op: in
              value_type: normalize
              value: "ipv6"

This policy will find all load balancers with 1000 or less transmitted packets over the last 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-inactive-loadbalancer
        resource: azure.loadbalancer
        filters:
          - type: metric
            metric: PacketCount
            op: le
            aggregation: total
            threshold: 1000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Inactive Load Balancer
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
