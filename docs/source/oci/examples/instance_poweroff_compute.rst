.. _instancepoweroffcompute:

Instance - Power off A Running Instance
=======================================

The following example policy will shut down a running instance

.. code-block:: yaml

    policies:
       - name: power-off-policy
         description: |
            Power off a compute instance
         resource: oci.instance
         filters:
           - type: value
             key: display_name
             value: Instance_1
         actions:
           - stop
