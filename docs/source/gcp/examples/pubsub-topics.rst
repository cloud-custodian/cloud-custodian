Pub/Sub - Audit Topics creation
===============================
Custodian can audit if a Pub/Sub Topic has been created. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy notifies users if the ``CreateTopic`` action appears in the logs.

.. code-block:: yaml

    policies:
      - name: gcp-pub-sub-topic-audit-creation
        resource: gcp.pubsub-topic
        mode:
          type: gcp-audit
          methods:
            - "google.pubsub.v1.Publisher.CreateTopic"
        actions:
         - type: notify
           to:
             - email@address
           format: txt
           transport:
             type: pubsub
             topic: projects/my-gcp-project/topics/my-topic
