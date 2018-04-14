.. _s3denypublicobjectacls:

S3 - Block Public S3 Object ACLs
=================================================

The following example policies will append a S3 bucket policy to every S3 bucket with
a policy statement called **DenyS3PublicObjectACL**  This will prevent any object
in these buckets from being set to public-read, public-read-write
,or authenticated-read (Any authenticated AWS user, not just local to account).
Being that S3 object permissions can be hard to track and restrict due to the huge
amount of S3 objects usually present in accounts, this policy allows you to prevent
the issue from occuring in the first place and helps maintain tighter S3 security
to avoid accidentally setting sensitive S3 objects to public.

.. code-block:: yaml

   policies:

     - name: s3-deny-public-object-acl-poll
       resource: s3
       description: |
         Appends a bucket policy statement to all existing s3 buckets to
         deny anyone from setting s3 objects in the bucket to public-read,
         public-read-write, or any authenticated AWS user.
       actions:
         - type: set-statements
           statements:
              - Sid: "DenyS3PublicObjectACL"
                Effect: "Deny"
                Action: "s3:PutObjectAcl"
                Principal: "*"
                Resource:
                   - "arn:aws:s3:::{bucket_name}/*"
                   - "arn:aws:s3:::{bucket_name}"
                Condition:
                  StringEqualsIgnoreCaseIfExists:
                     's3:x-amz-acl':
                         - "public-read"
                         - "public-read-write"
                         - "authenticated-read"


     - name: s3-deny-public-object-acl-realtime
       resource: s3
       mode:
         type: cloudtrail
         events:
           - CreateBucket
           - source: 's3.amazonaws.com'
             event: PutBucketPolicy
             ids: "requestParameters.bucketName"
         role: arn:aws:iam::{account_id}:role/Cloud_Custodian_Role
         timeout: 200
       description: |
         Appends a bucket policy statement to an s3 bucket when it detects
         a policy change to the bucket or a new bucket is created which
         will deny anyone from setting s3 objects in the bucket to public-read,
         public-read-write, or any authenticated AWS user.
       actions:
         - type: set-statements
           statements:
             - Sid: "DenyS3PublicObjectACL"
               Effect: "Deny"
               Action: "s3:PutObjectAcl"
               Principal: "*"
               Resource:
                  - "arn:aws:s3:::{bucket_name}/*"
                  - "arn:aws:s3:::{bucket_name}"
               Condition:
                 StringEqualsIgnoreCaseIfExists:
                    's3:x-amz-acl':
                        - "public-read"
                        - "public-read-write"
                        - "authenticated-read"

