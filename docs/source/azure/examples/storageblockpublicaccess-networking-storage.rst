Storage - Block public access
=============================

.. code-block:: yaml

    policies:
      - name: storage-block-public-access
        description: |
            Blocks public access to storage accounts with defined IP access rules.
        resource: azure.storage
        
        filters:
        - type: value
          key: properties.networkAcls.ipRules
          value_type: size
          op: ne
          value: 0

        actions:
        - type: set-firewall-rules
          default-action: Deny
          ip-rules: []
