Find Stopped Virtual Machines
=============================

.. code-block:: yaml

     policies:
       - name: vms-with-public-ip
         resource: azure.vm
         filters:
          - type: network-interface
            key: 'properties.ipConfigurations[].properties.publicIPAddress.id'
            op: eq
            value: not-null
