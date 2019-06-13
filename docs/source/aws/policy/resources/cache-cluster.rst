.. _cache-cluster:

ElastiCache Clusters
====================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

Actions
-------

``delete``
  Delete ElastiCache cluster and any associated replication group.
  You can specify if you want to ``skip-snapshot``, default is False

  .. c7n-schema:: aws.cache-cluster.actions.delete

``snapshot``
  Create a manual ElastiCache cluster snapshot

  .. c7n-schema:: aws.cache-cluster.actions.snapshot

