.. _buckettagpublicstorage:

Bucket - Tag all the buckets which has public access
====================================================

The following example policy will tag all the buckets which has public access

.. code-block:: yaml

    policies:
    - name: tag-public-buckets
      description: Tag all the public buckets in the tenancy
      resource: oci.bucket
      filters:
       - type: attributes
         key:  public_access_type
         value: 'ObjectRead'
         op: eq
      actions:
       - type: update
         freeform_tags:
           'public_access': 'true'
