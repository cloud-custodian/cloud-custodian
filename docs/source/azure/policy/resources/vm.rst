.. _azure_vm:

Virtual Machines
================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
- Arm Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor - (see `Virtual Machine Supported Metrics <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics#microsoftcomputevirtualmachines/>`_)
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- ``instance-view``
  Filter based on VM attributes in instance view, such as power state.

  .. c7n-schema:: azure.vm.filters.instance-view

- ``metric``
  Filter based on metrics from Azure Monitor, such as CPU usage.

  .. c7n-schema:: azure.vm.filters.metric


- ``network-interface``
  Filter based on properties of the network interfaces associated with the virtual machine.

  .. c7n-schema:: azure.vm.filters.network-interface

- ``off-hours and on-hours``
  Filter based on on-hour and off-hour configurations (see :ref:`offhours`)

Actions
-------
- ``start``
  Start the VMs

  .. c7n-schema:: azure.vm.actions.start


- ``poweroff``
  Stop the VMs

  .. c7n-schema:: azure.vm.actions.poweroff


- ``stop``
  Stop the VMs and deallocate resources

  .. c7n-schema:: azure.vm.actions.stop


- ``restart``
  Restart the VMs

  .. c7n-schema:: azure.vm.actions.restart


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

This policy will find all VMs that have Percentage CPU usage >= 75% over the last 72 hours

.. code-block:: yaml

    policies:
      - name: busy-vms
        resource: azure.vm
        filters:
          - type: metric
            metric: Percentage CPU
            op: ge
            aggregation: average
            threshold: 75
            timeframe: 72

This policy will find all VMs that have Percentage CPU usage <= 1% over the last 72 hours, mark for deletion in 7 days

.. code-block:: yaml

    policies:
      - name: delete-unused-vms
        resource: azure.vm
        filters:
          - type: metric
            metric: Percentage CPU
            op: le
            aggregation: average
            threshold: 1
            timeframe: 72
         actions:
          - type: mark-for-op
            op: delete
            days: 7
