App Engine - Audit application changes
=======================================
Custodian can audit application changes (e.g. a new version has been deployed). Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy notifies users if the ``UpdateService`` action appears in the logs.

.. code-block:: yaml

    policies:
      - name: gcp-app-engine-audit-application-updates
        resource: gcp.app-engine
        mode:
          type: gcp-audit
          methods:
            - "google.appengine.v1.Services.UpdateService"
        actions:
          - type: notify
            subject: New domain mapping added
            to:
              - email@address
            format: txt
            transport:
              type: pubsub
              topic: projects/my-gcp-project/topics/my-topic
