.. _instanceresizescompute:

Instance - Resize the instances based on the shape and CPU utilization
======================================================================

The following example policy will filter the instances that are using VM Standard shape with low CPU utilization.
And resize those instances to Flex shape.

.. code-block:: yaml

    policies:
      - name: perform-resize-on-compute
        description: Perform resize on the VM's only if the VM is tagged and it's maximum CPU utilization is less than 50%
        resource: oci.instance
        filters:
          - type: metrics
            query: 'CpuUtilization[1d].max() < 50'
          - type: value
            key: freeform_tags.eligible_for_resize
            value: 'true'
        actions:
          - type: remove-tag
            freeform_tags: ['eligible_for_resize']
          - type: update
            shape: VM.Standard.E3.Flex
            shape_config:
               ocpus: 1
