.. _rds-cluster-snapshot:

Relational Database Service DB Cluster Snapshots (RDS DB Cluster Snapshots)
===========================================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days
  **Deprecated** use value filter with `value_type: age`

  .. c7n-schema:: aws.rds-cluster-snapshot.filters.age


Actions
-------

``delete``
  Delete DB cluster snapshot

  .. c7n-schema:: aws.rds-cluster-snapshot.actions.delete

