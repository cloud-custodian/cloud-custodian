Find Stopped Virtual Machines
=============================

.. code-block:: yaml

     policies:
       - name: stopped-vm
         resource: azure.vm
         filters:
          - type: instance-view
            key: statuses[].code
            op: not-in
            value_type: swap
            value: "PowerState/running"

