Entra ID - Comprehensive User Security Audit
============================================

Find enabled guest users for security review according to CIS Azure 1.2.

.. code-block:: yaml

    policies:
      - name: security-audit-guest-users
        resource: azure.entraid-user
        description: |
          Comprehensive security audit for guest users.
          Finds enabled guest users for security review.
          CIS Azure 1.2 - Ensure that there are no guest users (or review them regularly).
        filters:
          - type: value
            key: userType
            value: Guest
          - type: value
            key: accountEnabled
            value: true

Find users who haven't signed in for more than 90 days.

.. code-block:: yaml

    policies:
      - name: security-audit-inactive-users
        resource: azure.entraid-user
        description: |
          Find users who haven't signed in for more than 90 days.
          These accounts may need to be disabled for security purposes.
          Note: Requires sign-in activity data to be available.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: last-sign-in
            days: 90
            op: greater-than

Find privileged users without MFA enabled.

.. code-block:: yaml

    policies:
      - name: security-audit-privileged-no-mfa
        resource: azure.entraid-user
        description: |
          Find privileged users without MFA enabled.
          Identifies high-risk accounts that need immediate attention.
          Note: Requires UserAuthenticationMethod.Read.All permission.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: value
            key: jobTitle
            value: ".*[Aa]dmin.*"
            op: regex
          - type: mfa-enabled
            value: false

Find users with passwords older than 180 days.

.. code-block:: yaml

    policies:
      - name: security-audit-old-passwords
        resource: azure.entraid-user
        description: |
          Find users with passwords older than 180 days.
          These accounts may need password rotation.
          Note: Requires password change date information.
        filters:
          - type: value
            key: accountEnabled
            value: true
          - type: password-age
            days: 180
            op: greater-than
