DNS - Notify if Logging is Disabled in DNS Policy
=================================================

A policy is a collection of DNS rules applied to one or more Virtual Private Cloud resources. Custodian can check logging state in DNS policies and report those which violate an established logging convention.

Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
        - name: gcp-dns-policies-notify-if-logging-disabled
          resource: gcp.dns-policy
          filters:
            - type: value
              key: enableLogging
              value: false
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/dns
