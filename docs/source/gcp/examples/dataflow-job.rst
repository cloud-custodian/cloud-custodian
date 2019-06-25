Dataflow -  Check for Hanged Jobs
====================================

Once started, a job in the Cloud Dataflow service transits from state to state and normally enters a terminal state. Custodian can check if there are any jobs hanging in temporary statuses abnormally long. 
 
Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

In the example below, the policy checks if there are any jobs which started over 1 day ago (configurable period) but not yet transitioned to a certain stable state for some reason (remains in ``JOB_STATE_RUNNING``, ``JOB_STATE_DRAINING``, ``JOB_STATE_CANCELLING`` statuses) and therefore may need administrator's attention.

.. code-block:: yaml

    policies:
      - name: gcp-dataflow-jobs-update
        resource: gcp.dataflow-job
        filters:
          - type: value
            key: startTime
            op: greater-than
            value_type: age
            value: 1
          - type: value
            key: currentState
            value: [JOB_STATE_RUNNING, JOB_STATE_DRAINING, JOB_STATE_CANCELLING]
        actions:
          - type: notify
            to:
              - email@address
            format: json
            transport:
              type: pubsub
              topic: projects/cloud-custodian/topics/dataflow
