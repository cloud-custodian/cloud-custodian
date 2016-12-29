.. _ebs-snapshot:

Elastic Block Store Snapshots (EBS Snapshots)
=============================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``StartTime`` of the snapshot, the time stamp when the snapshot was initiated, in days

  .. c7n-schema:: SnapshotAge
      :module: c7n.resources.ebs

Actions
-------

``delete``
  Delete EBS Snapshot based on ``skip-ami-snapshots``

  .. c7n-schema:: SnapshotDelete
      :module: c7n.resources.ebs
