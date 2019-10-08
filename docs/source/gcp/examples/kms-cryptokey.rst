Key Management System - Audit Crypto Key protection level
=========================================================

Cloud KMS allows to create and manage cryptographic keys in one central cloud service. Custodian can audit and notify if any of KMS cryptographic keys have been created using the wrong settings.

Note that the ``notify`` action requires a Pub/Sub topic to be configured. To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

In the example below, the policy filters and reports keys with protection level other than Hardware Security Module (HSM).

.. code-block:: yaml

    policies:
        - name: gcp-kms-cryptokey-audit-creation
          resource: gcp.kms-cryptokey
          mode:
            type: gcp-audit
            methods:
              - CreateCryptoKey
          filters:
            - type: value
              key: primary.protectionLevel
              op: not-in
              value:
                - HSM
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/my-gcp-project/topics/my-topic
