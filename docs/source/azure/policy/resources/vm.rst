.. _azure_vm:

Virtual Machines
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)

``instance-view``
  Filter based on VM attributes

  .. c7n-schema:: InstanceViewFilter
       :module: c7n_azure.resources.vm

Actions
-------

``start``
  Start the VMs

``stop``
  Stop the VMs

``restart``
  Restart the VMs

``delete``
  Delete the VMs

Example Policies
----------------

Stop all running VMs

.. code-block:: yaml

    policies:
      - name: stop-running-vms
        resource: azure.vm
        filters:
          - type: instance-view
            key: statuses[].code
            op: in
            value_type: swap
            value: PowerState/running
        actions:
          - type: stop

Start all VMs

.. code-block:: yaml

    policies:
      - name: start-vms
        resource: azure.vm
        actions:
          - type: start

Restart all VMs

.. code-block:: yaml

    policies:
      - name: start-vms
        resource: azure.vm
        actions:
          - type: restart

Delete specific VM by name

.. code-block:: yaml

    policies:
      - name: stop-running-vms
        resource: azure.vm
        filters:
          - type: value
            key: name
            op: eq
            value_type: normalize
            value: fake_vm_name
        actions:
          - type: delete