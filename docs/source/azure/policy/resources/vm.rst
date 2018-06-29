.. _azure_vm:

Virtual Machines
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
- Arm Filters (see :ref:`azure_genericarmfilter`)

``instance-view``
  Filter based on VM attributes in instance view, such as power state.

  .. c7n-schema:: InstanceViewFilter
       :module: c7n_azure.resources.vm

``metric``
  Filter based on metrics from Azure Monitor, such as CPU usage.

  .. c7n-schema:: MetricFilter
       :module: c7n_azure.filters

``network-interface``
  Filter based on properties of the network interfaces associated with the virtual machine.

  .. c7n-schema:: NetworkInterfaceFilter
        :module: c7n_azure.resources.vm

Actions
-------

``start``
  Start the VMs

  .. c7n-schema:: VmStartAction
       :module: c7n_azure.resources.vm 

``stop``
  Stop the VMs

  .. c7n-schema:: VmStopAction
        :module: c7n_azure.resources.vm 

``restart``
  Restart the VMs

  .. c7n-schema:: VmRestartAction
        :module: c7n_azure.resources.vm 

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

Find all VMs with a Public IP address

.. code-block:: yaml

    policies:
      - name: vms-with-public-ip
        resource: azure.vm
        filters:
          - type: network-interface
            key: 'properties.ipConfigurations[].properties.publicIPAddress.id'
            value: not-null
