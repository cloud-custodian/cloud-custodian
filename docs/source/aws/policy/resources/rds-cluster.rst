.. _rds-cluster:

Relational Database Service DB Clusters (RDS DB Clusters)
=========================================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

Actions
-------

``delete``
  Delete DB cluster and optionally associated DB instances.
  You can specify if you want to ``skip-snapshot``, default is False
  You can specify if you want to ``delete-instances``, default is False

  .. c7n-schema:: aws.rds-cluster.actions.delete


``snapshot``
  Create a manual DB cluster snapshot

  .. c7n-schema:: aws.rds-cluster.actions.snapshot


``retention``
  Set the DB cluster backup retention period to ``days``

  .. c7n-schema:: aws.rds-cluster.actions.retention

