Spanner - Set IAM Policies
===========================

These policies update the IAM policy for spanner instances (`add-bindings`) and databases (`remove-bindings`), respectively.

.. code-block:: yaml

    policies:
      - name: gcp-spanner-instances-set-iam-policy
        resource: gcp.spanner-instance
        actions:
          - type: set-iam-policy
            add-bindings:
              - members:
                  - user:user1@test.com
                  - user:user2@test.com
                role: roles/owner
              - members:
                  - user:user3@gmail.com
                role: roles/viewer

      - name: gcp-spanner-database-instances-set-iam-policy
        resource: gcp.spanner-database-instance
        actions:
          - type: set-iam-policy
            remove-bindings:
              - members: "*"
                role: roles/owner
              - members:
                  - user:user3@gmail.com
                role: roles/viewer
