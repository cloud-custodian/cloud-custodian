.. _subnettagnetwork:

Subnet - Tag all the subnets in the tenancy
===========================================

The following example policy will tag all the subnets in the tenancy

.. code-block:: yaml

    policies:
    - name: tag-subnet
      description: |
        Tag all the subnets in the tenancy
      resource: oci.subnet
      actions:
       - type: update
         freeform_tags:
            TagName: TagValue
