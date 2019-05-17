Pub/Sub - Audit Subscriptions updates
=====================================
Custodian can audit if a Pub/Sub Subscription has been updated. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy notifies users if the ``UpdateSubscription`` action appears in the logs.

.. code-block:: yaml

    policies:
      - name: gcp-pub-sub-subscription-audit-update
        resource: gcp.pubsub-subscription
        mode:
          type: gcp-audit
          methods:
            - "google.pubsub.v1.Subscriber.UpdateSubscription"
        actions:
         - type: notify
           to:
             - email@address
           format: txt
           transport:
             type: pubsub
             topic: projects/my-gcp-project/topics/my-topic
