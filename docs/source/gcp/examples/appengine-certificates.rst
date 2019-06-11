App Engine - Check if an SSL Certificate is About to Expire
============================================================
Custodian can check and notify if an SSL certificate is about to expire. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy is set to filter certificates which expire in 60 days or less.

.. code-block:: yaml

    policies:
        - name: appengine-certificate-age
          description: |
            Check existing certificate
          resource: gcp.app-engine-certificate
          filters:
          - type: value
            key: expireTime
            op: less-than
            value_type: expiration
            value: 60
          actions:
           - type: notify
             subject: Certificates expiring in 60 days
             to:
               - email@address
             format: txt
             transport:
               type: pubsub
               topic: projects/my-gcp-project/topics/my-topic            
