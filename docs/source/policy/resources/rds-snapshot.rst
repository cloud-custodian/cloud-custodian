.. _rds-snapshot:

Relational Database Service DB Snapshots (RDS DB Snapshots)
===========================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days

  .. c7n-schema:: RDSSnapshotAge
      :module: c7n.resources.rds

Actions
-------

``delete``
  Delete DB Snapshot

  .. c7n-schema:: RDSSnapshotDelete
      :module: c7n.resources.rds
