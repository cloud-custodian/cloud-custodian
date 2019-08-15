.. _azure_examples_vm_with_public_ips:

Virtual Machines - Find Virtual Machines with public IP address
===============================================================

Filter to select all virtual machines with a public ip address

.. code-block:: yaml

     policies:
       - name: vms-with-public-ip
         resource: azure.vm
         filters:
          - type: network-interface
            key: 'properties.ipConfigurations[].properties.publicIPAddress.id'
            value: not-null
