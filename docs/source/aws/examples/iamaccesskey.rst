IAM - Manage Access Keys
========================

List all IAM Access Keys:

.. code-block:: yaml

  policies:
    - name: all-iam-access-keys
      resource: iam-access-key

Filter by Access Key status (e.g. only active keys):

.. code-block:: yaml

  policies:
    - name: active-iam-access-keys
      resource: iam-access-key
      filters:
        - type: value
          key: Status
          value: Active

Filter Access Keys by username:

.. code-block:: yaml

  policies:
    - name: iam-access-keys-for-user
      resource: iam-access-key
      filters:
        - type: value
          key: UserName
          value: <insert-username-here>

Filter Access Keys by creation date:

.. code-block:: yaml

  policies:
    - name: old-iam-access-keys
      resource: iam-access-key
      filters:
        - type: value
          key: CreateDate
          value_type: age
          value: 90
          op: greater-than
