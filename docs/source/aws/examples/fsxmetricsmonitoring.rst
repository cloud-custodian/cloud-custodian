Filtering FSx based on CloudWatch metrics 
=========================================

Find FSx file systems with high CPU utilization
-----------------------------------------------

Retrieve FSx file systems that have sustained high CPU utilization over the last 7 days:

.. code-block:: yaml

    policies:
      - name: fsx-high-cpu-utilization
        resource: fsx
        description: |
          Find FSx file systems with sustained high CPU utilization
          over the last 7 days
        filters:
        - type: metrics
            name: CPUUtilization
            value: 80
            op: gte
            days: 7
            statistics: Average
