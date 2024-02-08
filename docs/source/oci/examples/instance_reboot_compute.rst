.. _instancerebootcompute:

Instance - Restart a Compute Instance
=====================================

The following example policy will restart a compute instance

.. code-block:: yaml

    policies:
        - name: reboot-instance
          description: |
             Restart a compute instance
          resource: oci.instance
          filters:
             - type: value
               key: display_name
               value: Instance_1
          actions:
             - reboot
