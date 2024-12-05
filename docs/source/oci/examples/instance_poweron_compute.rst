.. _instancepoweroncompute:

Instance - Power on a stopped Instance
======================================

The following example policy will start a stopped instance

.. code-block:: yaml

    policies:
        - name: power-on-policy
          description: |
             Power on a compute instance
          resource: oci.instance
          filters:
             - type: value
               key: display_name
               value: Instance_1
          actions:
             - start
