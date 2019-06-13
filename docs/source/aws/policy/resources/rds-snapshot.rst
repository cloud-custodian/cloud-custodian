.. _rds-snapshot:

Relational Database Service DB Snapshots (RDS DB Snapshots)
===========================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days
  **Deprecated** use value filter with `value_type: age`
  .. c7n-schema:: aws.rds.filters.age


Actions
-------

``delete``
  Delete DB Snapshot

  .. c7n-schema:: aws.rds.actions.delete

