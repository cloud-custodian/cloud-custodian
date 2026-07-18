IAM - Manage Whether A Specific IAM Policy is Attached to Roles
===============================================================

Attach required IAM policy to Roles without it:

.. code-block:: yaml

  policies:
    - name: iam-attach-policy
      resource: iam-role
      filters:
        - type: no-specific-managed-policy
          value: my-iam-policy
      actions:
        - type: set-policy
          state: attached
          arn: arn:aws:iam::123456789012:policy/my-iam-policy

Detach undesired IAM policy from Roles with it:

.. code-block:: yaml

  policies:
    - name: iam-detach-policy
      resource: iam-role
      filters:
        - type: has-specific-managed-policy
          value: my-iam-policy
      actions:
        - type: set-policy
          state: detached
          arn: arn:aws:iam::123456789012:policy/my-iam-policy
