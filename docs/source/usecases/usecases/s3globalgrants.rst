S3 - Global Grants
==================

Scan buckets that allow for global access in their
ACLs and report them and the ACL permissions granted.


.. code-block:: yaml

   policies:

     - name: s3-insecure-grants
       action: global-grants
       resource: s3
