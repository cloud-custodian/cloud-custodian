Pub/Sub - Check if there are expiring Snapshots
===============================================
Custodian can check if a Pub/Sub Snapshot expires in a set number of days. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy notifies users if there are Snapshots expiring in 2 days.

.. code-block:: yaml

    policies:
      - name: gcp-pub-sub-snapshots-notify-if-expiring
        resource: gcp.pubsub-snapshot
        filters:
          - type: value
            key: expireTime
            op: less-than
            value_type: expiration
            value: 2
        actions:
         - type: notify
           to:
             - email@address
           format: txt
           transport:
             type: pubsub
             topic: projects/my-gcp-project/topics/my-topic
