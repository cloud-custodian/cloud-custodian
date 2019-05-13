.. _cache-snapshot:

ElastiCache Cluster Snapshots
=============================
Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``SnapshotCreateTime`` of the snapshot, the time stamp when the snapshot was created, in days

  .. c7n-schema:: ElastiCacheSnapshotAge
      :module: c7n.resources.elasticache

Actions
-------

``delete``
  Delete ElastiCache cluster snapshot

  .. c7n-schema:: DeleteElastiCacheSnapshot
      :module: c7n.resources.elasticache
