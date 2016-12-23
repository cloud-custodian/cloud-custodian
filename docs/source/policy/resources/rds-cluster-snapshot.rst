.. _rds-cluster-snapshot:

Relational Database Service DB Cluster Snapshots (RDS DB Cluster Snapshots)
===========================================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days

  .. c7n-schema:: RDSSnapshotAge
      :module: c7n.resources.rdscluster

Actions
-------

``delete``
  Delete DB cluster snapshot

  .. c7n-schema:: RDSClusterSnapshotDelete
      :module: c7n.resources.rdscluster
