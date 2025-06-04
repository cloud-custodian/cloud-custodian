.. _efspolicystatements:

EFS - Policy Statements with has-statement and PartialMatch
===========================================================

The following example policy looks for an exact match for the `Allow` statement.

.. code-block:: yaml

    policies:
      - name: efs-has-statement
        resource: aws.efs
        filters:
          - type: has-statement
            statements:
              - Effect: Allow
                Action:
                  - elasticFilesystem:clientRootAccess


The has-statement filter will only return resources with policy
statements that **exactly** match the provided keys in `has-statement`, so
only statements with the single action `elasticFilesystem:clientRootAccess`
will be returned. The statement can have other fields such as condition, but
the `Action` key can only include `elasticFilesystem:clientRootAccess`.

For example, EFS resources with the following policy statement will be
returned::

  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
            "AWS": "*"
        },
        "Action": "elasticfilesystem:ClientRootAccess",
        "Condition": {
            "Bool": {
                "elasticfilesystem:AccessedViaMountTarget": "true"
            }
        }
      }
    ]
  }


PartialMatch
************

The following example policy workflow uses the `has-statement` filter with the
`PartialMatch` field which will match any statement that **includes** the
`Action` listed, rather than only resources that **exactly match** the items in
the `Action` key.

.. code-block:: yaml

    policies:
      - name: efs-has-statement-partial-match
        resource: aws.efs
        filters:
          - type: has-statement
            statements:
              - Effect: Allow
                Action:
                  - elasticFilesystem:clientRootAccess
                PartialMatch:
                  - Action


For example, resources with the following policy statement would be returned
since it **partially matches** the `Action` field::

  {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "*"
            },
            "Action": [
                "elasticfilesystem:ClientRootAccess",
                "elasticfilesystem:ClientWrite"
            ],
        }
    ]
  }
