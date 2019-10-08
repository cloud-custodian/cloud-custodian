Network Security Groups - Deny access to Network Security Group
===============================================================

This policy will deny access to all ports that are NOT 22, 23 or 24 for all Network Security Groups
For more examples see :ref:`azure.networksecuritygroup`

.. code-block:: yaml

      policies:
       - name: close-inbound-except-22-24
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            exceptPorts: '22-24'
            match: 'any'
            access: 'Allow'
         actions:
          - type: close
            exceptPorts: '22-24'
            direction: 'Inbound'

