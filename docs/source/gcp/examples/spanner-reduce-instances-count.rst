Spanner - Reduce Count of Instance Nodes
=========================================

This policy reduces the node count to 1 node for a spanner instance and then
notifies about the action taken via an email.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
      - name: gcp-spanner-instances-change-node-count
        resource: gcp.spanner-instance
        filters:
          - type: value
            key: nodeCount
            op: gte
            value: 2
        actions:
          - type: set
            nodeCount: 1
          - type: notify
            subject: The node count for spanner instances was updated
            to:
              - email@address
            transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/demo-notifications
