Find Virtual Machines with Public IP address
============================================

.. code-block:: yaml

     policies:
       - name: vms-with-public-ip
         resource: azure.vm
         filters:
          - type: network-interface
            key: 'properties.ipConfigurations[].properties.publicIPAddress.id'
            value: not-null
