Spanner - Filter Based on Metrics
=================================

This policy utilizes the Monitoring API to query all spanner instances, and then
filter them based on which are mostly idle ("less than 0.05 CPU utilization over
the last 14 days").

.. code-block:: yaml

    policies:
      - name: gcp-spanner-instances-mostly-idle
        resource: gcp.spanner-instance
        filters:
          - type: metrics
            name: spanner.googleapis.com/instance/cpu/utilization
            op: lte
            value: 0.05
            days: 14
            aligner: ALIGN_MEAN
