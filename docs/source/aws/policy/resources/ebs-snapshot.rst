.. _ebs-snapshot:

Elastic Block Store Snapshots (EBS Snapshots)
=============================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``StartTime`` of the snapshot, the time stamp when the snapshot was initiated, in days
  **Deprecated** use value filter with `value_type: age`
  .. c7n-schema:: aws.ebs.filters.age


Actions
-------

``delete``
  Delete EBS Snapshot based on ``skip-ami-snapshots``

  .. c7n-schema:: aws.ebs.actions.delete

