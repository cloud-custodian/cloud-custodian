Pub/Sub - Early Detection of Obsolete Snapshots
====================================================

In Cloud Pub/Sub, the snapshot feature allows users to capture the message acknowledgment state of a subscription to a topic. Once a snapshot is created, it retains all messages that were unacknowledged in the source subscription (at the time of the snapshot's creation).

All pubsub snapshots are deleted in a week or less of their creation. For some use cases it maybe useful to delete them earlier.

Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

In the example below, the policy reports existing snapshots whose topics have been deleted, therefore snapshots may need prompt deletion as well.

.. code-block:: yaml

    policies:
      - name: gcp-pub-sub-snapshots-notify-if-topic-deleted
        resource: gcp.pubsub-snapshot
        filters:
          - type: value
            key: topic
            value: _deleted-topic_
        actions:
         - type: notify
           to:
             - email@address
           format: txt
           transport:
             type: pubsub
             topic: projects/my-gcp-project/topics/my-topic
