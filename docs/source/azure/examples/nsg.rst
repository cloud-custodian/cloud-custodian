Deny access to Network Security Group.
======================================

This policy will deny access to all security rules with any Inbound SSH ports that are NOT 22, 23 or 24.
For more examples see :ref:`azure_nsg`

.. code-block:: yaml

      policies:
       - name: close-ingress-except-22-24
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            exceptPorts: [22,23,24]
         actions:
          - type: close

