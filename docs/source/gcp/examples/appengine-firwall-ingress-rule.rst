App Engine - Firewall ingress rules
====================================

Description

.. code-block:: yaml

    policies:
      - name: gcp-app-engine-firewall-ingress-rule-notify-if-default-unrestricted-access
        resource: gcp.app-engine-firewall-ingress-rule
        filters:
          - and:
            - type: value
              value_type: resource_count
              op: eq
              value: 1
            - type: value
              key: sourceRange
              value: '*'
            - type: value
              key: action
              value: ALLOW
        actions:
          - type: notify
            subject: App Engine has default unrestricted access
            to:
              - Pub/Sub
            transport:
              type: pubsub
              topic: projects/cloud-custodian-190204/topics/appengine-demo