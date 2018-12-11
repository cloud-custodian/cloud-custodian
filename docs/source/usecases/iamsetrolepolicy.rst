IAM - Attach Required IAM Policy To All Roles Without It
========================================================

.. code-block:: yaml

    - name: iam-attach-policy
      resource: iam-role
      filters:
        - type: no-specific-managed-policy
          value: my-iam-policy
      actions:
        - type: set-policy
          state: attached
          arn: arn:aws:iam::123456789012:policy:my-iam-policy
