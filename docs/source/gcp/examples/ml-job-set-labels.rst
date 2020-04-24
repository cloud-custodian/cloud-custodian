ML Engine - Set Labels to Jobs
===============================

Using labels is one of best practices to keep enterprise ML pipelines organized. Setting labels can serve as basis for consequential manipulations with resources (deletion, etc).

In the example below, Custodian sets "age" label of "obsolete" value for any ML jobs older than 5 days ago.

.. code-block:: yaml

    policies:
      - name: ml-job-set-labels
        resource: gcp.ml-job
        filters:
          - type: value
            key: createTime
            op: greater-than
            value_type: age
            value: 5
        actions:
          - type: set
            labels:
              age: obsolete
