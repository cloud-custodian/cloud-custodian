S3 - Encrypt All Objects
========================

Will scan all keys in the bucket for unencrypted keys and by default
remediate them such that they are encrypted.

.. code-block:: yaml

   policies:
     - name: s3-key-encryption
       resource: s3
       actions:
         - type: encrypt-keys
           crypto: aws:kms

Options
  ``crypto`` for determining the crypto mechanism, this can either be ``aws:kms`` or ``AES256`` (default)
  ``key-id`` for specifiying the customer KMS key to use for the SSE, if the ``crypto`` value passed is ``aws:kms`` the AWS default KMS key will be used instead.
  ``report-only`` generate reports of unencrypted keys in a bucket, but do not remediate them.
