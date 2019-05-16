App Engine - Check if a Firewall Rule is in Place
============================================================
Custodian can check and notify if App Engine firewall ingress rules have been mis-configured.

The policy below checks if a default ALLOW ingress rule is still active (e.g., somebody forgotten to remove it).

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
             format: txt
             transport:
               type: pubsub
               topic: projects/my-gcp-project/topics/my-topic
             
