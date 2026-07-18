Entra ID - Administrative Users by Job Title
============================================

Find users with job titles containing "Admin" using regex matching.

.. code-block:: yaml

    policies:
      - name: admin-users-by-job-title
        resource: azure.entraid-user
        description: |
          Find users with administrative job titles.
          This policy helps identify users who may have elevated privileges
          based on their job title field.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: value
            key: jobTitle
            value: ".*[Aa]dmin.*"
            op: regex
