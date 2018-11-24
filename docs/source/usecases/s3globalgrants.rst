S3 - Global Grants
==================

Scan buckets that allow for global access in their
ACLs and delete the associated ACL permissions.


.. code-block:: yaml

   policies:

   - name: s3-global-access
     resource: s3
     filters:
       - type: global-grants
     actions:
       - type: delete-global-grants
         grantees:
           - "http://acs.amazonaws.com/groups/global/AllUsers"
           - "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"
