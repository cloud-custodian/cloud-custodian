Cloud SQL - List Unsucessful Backups Older Than N Days
=======================================================

The following example demonstrates ability of Cloud Custodian to track backup runs of Cloud SQL instances and list unsuccessful backups (if any) older than 5 days.

.. code-block:: yaml

    policies:
    - name: sql-backup-run
      description: |
        check basic work of Cloud SQL filter on backup runs: lists unsucessful backups older than 5 days
      resource: gcp.sql-backup-run
      filters:
        - type: value
          key: status
          op: not-equal
          value: SUCCESSFUL
        - type: value
          key: endTime
          op: greater-than
          value_type: age
          value: 5
      actions:
        - type: notify
          to:
           - email@address
          # address doesnt matter
          format: txt
          transport:
            type: pubsub
            topic: projects/river-oxygen-233508/topics/first
