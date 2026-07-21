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

DNS - Enable DNSSEC on public zones
=====================================

Use the ``enable-dnssec`` action to turn on DNSSEC for public managed zones
that currently have it disabled.

.. code-block:: yaml

    policies:
        - name: gcp-dns-enable-dnssec
          resource: gcp.dns-managed-zone
          filters:
            - type: value
              key: visibility
              op: eq
              value: public
            - type: value
              key: dnssecConfig.state
              op: ne
              value: "on"
          actions:
            - type: enable-dnssec

DNS - Set DNSSEC key specifications on public zones
=====================================================

Use the ``set-dnssec-key-specs`` action to enable DNSSEC and configure the
key-signing (KSK) and zone-signing (ZSK) algorithms in one step.

Valid ``keyType`` values: ``keySigning``, ``zoneSigning``

Valid ``algorithm`` values: ``rsasha1``, ``rsasha256``, ``rsasha512``,
``ecdsap256sha256``, ``ecdsap384sha384``

.. code-block:: yaml

    policies:
        - name: gcp-dns-set-dnssec-key-specs
          resource: gcp.dns-managed-zone
          filters:
            - type: value
              key: visibility
              op: eq
              value: public
            - type: value
              key: dnssecConfig.state
              op: ne
              value: "on"
          actions:
            - type: set-dnssec-key-specs
              defaultKeySpecs:
                - keyType: keySigning
                  algorithm: rsasha256
                  keyLength: 2048
                - keyType: zoneSigning
                  algorithm: rsasha256
                  keyLength: 1024
