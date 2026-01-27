.. _bucketaccessstorage:

Bucket - Change the visibility of the bucket to Private
=======================================================

The following example policy will filter all the buckets based on a tag and sets the visibility to private

.. code-block:: yaml

    policies:
    - name: set-private-bucket
      description: Filter the buckets and set the visibility to private
      resource: oci.bucket
      filters:
       - type: value
         key: "freeform_tags.public_access"
         value: 'true'
         op: eq
      actions:
       - type: update
         public_access_type: 'NoPublicAccess'
