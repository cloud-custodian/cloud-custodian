S3 - Encryption
===============

Enable Bucket Encryption
------------------------

The following policy will enable bucket encryption on all s3 buckets.

.. code-block:: yaml

   policies:
     - name: s3-set-bucket-encryption
       resource: s3
       actions:
         - type: set-bucket-encryption
           crypto: AES256
           enabled: True


Remediate Existing
------------------

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
+++++++

  - ``crypto`` for determining the crypto mechanism, this can either be
    ``aws:kms`` or ``AES256`` (default)

  - ``key-id`` for specifying the customer KMS key to use for the SSE, if the
    ``crypto`` value passed is ``aws:kms`` the AWS default KMS key will be used
    instead.

  - ``report-only`` generate reports of unencrypted keys in a bucket, but do
    not remediate them.


Remediate Incoming
------------------

Note: the ``set-bucket-encryption`` action is a much more effective way of
enabling encryption on a bucket.

Will scan all newly created objects and remediate them such that they are
encrypted.

.. code-block:: yaml

   policies:
     - name: s3-attach-encryption
       resource: s3
       actions:
         - type: attach-encrypt
           role: arn:aws:iam::123456789012:role/my-role
           topic: arn:aws:sns::123456789012:my-topic

Options
+++++++

  - ``role`` for the role the encrypting Lambda should run as (not necessary if
    you provide ``--assume-role`` on the command line).

  - ``topic`` for the SNS topic to subscribe the Lambda to. If you set
    ``topic`` to ``default`` then we will reuse any existing SNS topic that
    specifies ``s3:ObjectCreated:*``, or set one up if needed. If ``topic`` is
    missing, then we'll attach via a bucket notification.


Bucket Policy
-------------

Note: the ``set-bucket-encryption`` action is a much more effective way of
enabling encryption on a bucket.

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
