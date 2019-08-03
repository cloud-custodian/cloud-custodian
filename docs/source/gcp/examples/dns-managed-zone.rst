DNS - Notify if DNS Managed Zone has no DNSSEC
==============================================

A ManagedZone is a resource that represents a DNS zone hosted by the Cloud DNS service. Custodian can check if DNSSEC is disabled in DNS Managed Zone which may violate security policy of an organization.

Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
        - name: gcp-dns-managed-zones-notify-if-no-dnssec
          resource: gcp.dns-managed-zone
          filters:
            - type: value
              key: dnssecConfig.state
              # off without quotes is treated as bool False
              value: "off"
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/dns
