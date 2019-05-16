App Engine - Audit domain mappings being added
===============================================
Custodian can audit new mappings being added. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy notifies users if the ``CreateDomainMapping`` action appears in the logs.

.. code-block:: yaml

    policies:
      - name: gcp-app-engine-domain-mapping-audit-new-mappings
        resource: gcp.app-engine-domain-mapping
        mode:
          type: gcp-audit
          methods:
            - "google.appengine.v1beta.DomainMappings.CreateDomainMapping"
        actions:
          - type: notify
            subject: New domain mapping added
            to:
              - email@address
            format: txt
            transport:
              type: pubsub
              topic: projects/my-gcp-project/topics/my-topic
