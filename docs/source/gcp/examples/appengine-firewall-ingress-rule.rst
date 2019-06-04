App Engine - Check if a Firewall Rule is in Place
==================================================
Custodian can check and notify if App Engine firewall ingress rules have been mis-configured. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy checks that there is only one rule allowing all connections.

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
             to:
               - email@address
             subject: App Engine has default unrestricted access
             format: txt
             transport:
               type: pubsub
               topic: projects/my-gcp-project/topics/my-topic


In this variant, the policy checks if a custom DENY rule is in place and notify if absent.

.. code-block:: yaml

    policies:
        - name: appengine-firewall-rules
          description: |
            Check absence of a required firewall rule
          resource: gcp.app-engine-firewall-ingress-rule
          filters:
          - type: value
            key: sourceRange
            value: 192.168.2.0/24
            op: absent
          - type: value
            key: action
            value: DENY
          actions:
           - type: notify
             to:
               - email@address
             subject: A required firewall rule is missing
             format: txt
             transport:
               type: pubsub
               topic: projects/my-gcp-project/topics/my-topic
