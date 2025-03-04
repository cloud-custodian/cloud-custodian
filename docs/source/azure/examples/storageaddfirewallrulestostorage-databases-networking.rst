.. _azure_examples_add_firewall_rules_to_storage:

Storage - Add storage firewall rules
====================================

Finds storage accounts with no ip rules and modifies them to:
- Deny public access
- Enable Logging and Metrics access to the database
- Allow access from the locations specified by ``ip-rules`` and ``virtual-network-rules``

.. code-block:: yaml

   policies:
       - name: add-storage-firewall
         description: |
             Find storage accounts without open ip list and restrict them.
         resource: azure.storage

         filters:
           - type: value
             key: properties.networkAcls.ipRules
             value_type: size
             op: eq
             value: 0

         actions:
           - type: set-firewall-rules
             default-action: Deny
             bypass-rules: [Logging, Metrics]
             ip-rules:
                 - 11.12.13.14
                 - 21.22.23.24
             virtual-network-rules:
                 - /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/subnet1
                 - /subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet2/subnets/subnet2

Finds storage account with no ip rules and modifies it to:
- Enable Logging and Metrics access to the database
- Allow access from the location specified by ``ip-rules``

Note: Because this policy leaves the storage account open to access by all 
ip addresses, the new rules will have no effect on the performance until 
the ``default-action`` is set to Deny.

.. code-block:: yaml

   policies:
       - name: add-inactive-storage-firewall
         description: |
           Find storage accounts without open ip list and add some rules. The rules will be stored as inactive and can be activated later.
         resource: azure.storage

         filters:
           - type: value
             key: properties.networkAcls.ipRules
             value_type: size
             op: eq
             value: 0

         actions:
           - type: set-firewall-rules
             default-action: Allow
             bypass-rules: [Logging, Metrics]
             ip-rules:
                 - 11.12.13.14
                 - 21.22.23.24
