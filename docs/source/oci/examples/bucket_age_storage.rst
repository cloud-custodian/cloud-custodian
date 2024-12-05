.. _bucketagestorage:

Bucket - Filter the buckets whose age is greater than 100 days
==============================================================

The following example policy will filter all the buckets whose age is greater than 100 days and tag them with the specified value

.. code-block:: yaml

    policies:
    - name: set-tag-on-bucket
      description: |
        Filter the buckets based on the age and tag them
      resource: oci.bucket
      filters:
       - type: value
         key: time_created
         value_type: age
         op: gt
         value: 100
      actions:
       - type: update
         freeform_tags:
            'cloud_custodian': 'true'
