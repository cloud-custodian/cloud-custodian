App Engine - Check if a Firewall Rule is in Place
==================================================
Custodian can check and notify if App Engine firewall ingress rules have been misconfigured. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

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


In this variant, the policy checks if there are any firewall rules with ``sourceRange`` violating ``min-network-prefix-size``.

.. code-block:: yaml

    vars:
        min-network-prefix-size: &min-network-prefix-size 24

    policies:
        - name: appengine-firewall-rules
          description: |
            Check if firewall rule network prefix size is long enough
          resource: gcp.app-engine-firewall-ingress-rule
          filters:
            - not:
              - type: value
                key: sourceRange
                op: regex
                # filtering out the * special character and IP addresses without network prefix length
                value: "^([0-9]{1,3}\\.){3}[0-9]{1,3}(\\/([0-9]|[1-2][0-9]|3[0-2]))?$"
              - type: value
                key: sourceRange
                value_type: cidr_size
                op: ge
                value: *min-network-prefix-size
          actions:
           - type: notify
             to:
               - email@address
             subject: A required firewall rule is missing
             format: txt
             transport:
               type: pubsub
               topic: projects/my-gcp-project/topics/my-topic
