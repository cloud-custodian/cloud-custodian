Cloud SQL - Lists Unsucessful Backups Older Than N Days
=======================================================

TBD. list unsucessful backups older than 5 days

In the example below, TBD.

.. code-block:: yaml

policies:
    - name: leonid-sql-backup-run
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
