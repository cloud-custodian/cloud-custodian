Cloud Billing Accounts - Set IAM Policies
=========================================

The policy updates the IAM policy for Billing Accounts.

.. code-block:: yaml

    policies:
      - name: gcp-cloudbilling-account-set-iam-policy
        resource: gcp.cloudbilling-account
        actions:
          - type: set-iam-policy
            add-bindings:
              - members:
                  - user:user1@test.com
                  - user:user2@test.com
                role: roles/editor
            remove-bindings:
              - members: "*"
                role: roles/owner
