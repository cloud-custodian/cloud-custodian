.. _cache-snapshot:

ElastiCache Cluster Snapshots
=============================
Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days
  **Deprecated** use value filter with value_type: age

  .. c7n-schema:: aws.cache-snapshot.filters.age

Actions
-------

``delete``
  Delete ElastiCache cluster snapshot

  .. c7n-schema:: aws.cache-snapshot.actions.delete

