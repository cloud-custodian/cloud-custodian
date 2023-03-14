S3 - Add lifecycle policy on bucket delete
==========================================

When a bucket is attempted to be deleted, add a lifecycle policy to empty the bucket. This is useful for more "ephemeral" environments to allow for async deletion of bucket objects which removes the need for consumers to manually empty buckets.

Permissions required:

- `"s3:GetBucketTagging"`
- `"s3:GetLifecycleConfiguration"`
- `"s3:ListAllMyBuckets"`
- `"s3:PutLifecycleConfiguration"`


.. code-block:: yaml

  policies:
    - name: add-lifecycle-policy-on-bucket-delete
      comments: |
        In dev, let's start emptying the bucket as soon as delete is requested so that we can have a more ephmeral environment for standup/teardown
      resource: s3
      mode:
        type: cloudtrail
        events:
          - source: s3.amazonaws.com
            event: DeleteBucket
            ids: 'requestParameters.bucketName'
        # Default behavior bails early due to the error code of BucketNotEmpty being present.
        environment:
          Variables:
            C7N_SKIP_ERR_EVENT: 'no'
      # Only put policy on buckets that have the env = dev tag for safety to ensure only "dev" environment buckets are targeted.
      filters:
        - tag:env: dev
      actions:
        - type: configure-lifecycle
          rules:
            - ID: empty-bucket
              Status: Enabled
              Filter:
                Prefix: ''
              Expiration:
                Days: 1
              NoncurrentVersionExpiration:
                NoncurrentDays: 1
