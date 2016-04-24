S3 - Encrypt All Objects
========================

Will scan all keys in the bucket for unencrypted keys and by default
remediate them such that they are encrypted.

.. code-block:: yaml

   policies:
     - name: s3-key-encryption
       resource: s3
       actions:
         - encrypt-keys


Options
  ``crypto`` for determining the crypto mechanism, this can either be ``AWS:KMS`` or ``AES256`` (default)
  ``report-only`` generate reports of unencrypted keys in a bucket, but do not remediate them.
