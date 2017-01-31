S3 - Encryption Bucket Policy
=============================

Adds an encryption required bucket policy and merges with extant policy
statements. Note filters should be used to avoid hitting any buckets
that are being written to by AWS services, as these do not write
encrypted and will be blocked by this policy.

.. code-block:: yaml

   policies:
     - name: s3-encryption-policy
       resource: s3
       actions:
        - encryption-policy
