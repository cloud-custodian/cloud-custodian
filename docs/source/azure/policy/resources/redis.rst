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

This set of policies will mark all CDNs for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-cdn-for-deletion
        resource: azure.cdn
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
      - name: delete-test-cdn
        resource: azure.cdn
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all Redis caches with more than 1000 cache misses in the last 72 hours

.. code-block:: yaml

    policies:
      - name: notify-redis-cache-misses
        resource: azure.redis
        filters:
          - type: metric
            metric: cachemisses
            op: ge
            aggregation: count
            threshold: 1000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Many Cache Misses
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
