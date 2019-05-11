App Engine - Check if a Required Firewall Rule is in Place
============================================================
-   Custodian can check and notify if App Engine firewall rules have been changed, removed or mis-configured.

.. code-block:: yaml

    policies:
        - name: appengine-firewall-rules
          description: |
            Check exisiting firewall rules
          resource: gcp.app-engine-firewall-ingress-rule
          filters:
          - type: value
            key: sourceRange
            value: 192.168.2.0/24
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
             
