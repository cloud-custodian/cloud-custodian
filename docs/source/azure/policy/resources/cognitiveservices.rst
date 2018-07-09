.. _azure_cognitiveservices:

Cognitive Services
==================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `CognitiveServicesAccount <https://docs.microsoft.com/en-us/python/api/azure.mgmt.cognitiveservices.models.cognitiveservicesaccount?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Cognitive Services Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcognitiveservicesaccounts/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource

Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This set of policies will mark all Cognitive Services accounts for deletion in 7 days that have 'test' in name (ignore case),
and then perform the delete operation on those ready for deletion.

.. code-block:: yaml

    policies:
      - name: mark-test-cogserv-for-deletion
        resource: azure.cognitiveservice
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
      - name: delete-test-cogserv
        resource: azure.cognitiveservice
        filters:
          - type: marked-for-op
            op: delete
        actions:
          - type: delete

This policy will find all Cognitive Service accounts with 1000 or more total errors over the 72 hours and notify user@domain.com

.. code-block:: yaml

    policies:
      - name: notify-cogserv-many-failures
        resource: azure.cognitiveservice
        filters:
          - type: metric
            metric: TotalErrors
            op: ge
            aggregation: total
            threshold: 1000
            timeframe: 72
         actions:
          - type: notify
            template: default
            priority_header: 2
            subject: Cognitive Services with Errors
            to:
              - user@domain.com
            transport:
              - type: asq
                queue: https://accountname.queue.core.windows.net/queuename
