Remove public storage IP-s
==========================

.. code-block:: yaml

    policies:
        - name: storage-no-public-ip
        description: |
            Find publicly available storage ip-s and remove them while keeping the virtual network access intact.
        resource: azure.storage
        
        filters:
        - type: value
          key: properties.networkAcls.ipRules
          value_type: size
          op: ne
          value: 0

        actions:
        - type: set-network-rules
          default-action: Deny
          ip-rules: []
