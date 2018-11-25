.. _s3configurenewbucket:

S3 - Configure New Buckets Settings and Standards
=====================================================

The following example policy will automatically create a CloudWatch Event Rule
triggered Lambda function in your account and region which will be triggered
anytime a new S3 bucket is created in that region.  The policy then applies
several configurations such as enabling the default S3 AES256 bucket encryption,
turns on object versioning, creates a s3 object lifecycle, enables logging on the
bucket, and tags the user that created the bucket.  When using the toggle-logging
action as shown below you must make sure the s3 bucket the logs are getting sent
to already exists.  Buckets can only send logs to logging buckets in the same region
as it so you may need to create multiple logging buckets per account if you use more
than 1 region.  In the below example the logging buckets would be named using account
and region like the following:  0123456789012-us-east-1-s3-logs
The S3 bucket lifecycle will help to save S3 costs by getting rid of old object versions
and moving objects from standard storage class to infrequent access storage after 180
days in this example.


.. code-block:: yaml

   policies:

      - name: s3-configure-standards-real-time
        resource: s3
        description: | 
          This policy is triggered when a new S3 bucket is created and it applies
          the AWS AES256 Default Bucket Encryption, Tags the creators ID, enables
          object versioning, configures the bucket lifecycle and enables logging.
        mode:
          type: cloudtrail
          events:
            - CreateBucket
          role: arn:aws:iam::{account_id}:role/Cloud_Custodian_S3_Lambda_Role
          timeout: 200
        actions:
          - type: auto-tag-user
            tag: CreatorName
          - type: set-bucket-encryption
          - type: toggle-versioning
            enabled: true
          - type: toggle-logging
            target_bucket: "{account_id}-{region}-s3-logs"
            target_prefix: "{source_bucket_name}/"
          - type: configure-lifecycle
            rules:
             - ID: company-s3-lifecycle
               Status: Enabled
               Filter:
                  Prefix: /
               Transitions:
                 - Days: 180
                   StorageClass: STANDARD_IA
               NoncurrentVersionExpiration:
                   NoncurrentDays: 35


