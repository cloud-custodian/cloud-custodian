.. _s3denypublicobjectacls:

S3 - Block Public S3 Object ACLs
=================================================

The following example policy will append a S3 bucket policy to every bucket which
is missing the bucket policy statement called **DenyS3PublicObjectACL**  This will
prevent any object in these buckets from being set to public-read, public-read-write
,or authenticated-read (Any authenticated AWS user, not just local to account).
Being that S3 object permissions can be hard to track and restrict due to the huge
amount of S3 objects usually present in accounts, this policy allows you to prevent
the issue from occuring in the first place and helps maintain tighter S3 security
to avoid accidentally setting sensitive S3 objects to public.

.. code-block:: yaml

   policies:

     - name: s3-deny-public-put-object-acl
       resource: s3
       filters:
         - not:
              - type: has-statement
                statements:
                 - Sid: "DenyS3PublicObjectACL"
       actions:
         - type: set-statements
           statements:
              - Sid: "DenyS3PublicObjectACL"
                Effect: "Deny"
                Action: "s3:PutObjectAcl"
                Principal: "*"
                Resource:
                   - "arn:aws:s3:::{bucket_name}/*"
                   - "arn:aws:s3:::{bucket_name}*"
                Condition:
                  StringEquals:
                     's3:x-amz-acl':
                         - "public-read"
                         - "public-read-write"
                         - "authenticated-read"

