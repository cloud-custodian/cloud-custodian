Pub/Sub - Audit Subscriptions to Match Requirements
===================================================

In Cloud Pub/Sub, subscriptions connect a topic to a subscriber application that receives and processes messages published to the topic. Custodian can find Pub/Sub subscriptions whose settings do not match the required ones. 

Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

In the example below, users are notified if the resources appearing in the logs with ``CreateSubscription`` or ``UpdateSubscription`` action have expiration policy unset.

.. code-block:: yaml

    policies:
      - name: gcp-pub-sub-subscription-audit
        resource: gcp.pubsub-subscription
        mode:
          type: gcp-audit
          methods:
            - "google.pubsub.v1.Subscriber.CreateSubscription"
            - "google.pubsub.v1.Subscriber.UpdateSubscription"
        filters:
          - type: value
            key: expirationPolicy.ttl
            value:
        actions:
         - type: notify
           to:
             - email@address
           format: txt
           transport:
             type: pubsub
             topic: projects/my-gcp-project/topics/my-topic
