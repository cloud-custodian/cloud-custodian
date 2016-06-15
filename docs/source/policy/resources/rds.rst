.. _rds:

Relational Database Service (RDS)
=================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``default-vpc``
  Check if RDS instance is in the Default VPC

Actions
-------

``delete``
  Delete DB instance.
  You can specify if you want to ``skip-snapshot``, default is False

``snapshot``
  Create a manual DB snapshot

``retention``
  Set the DB instance backup retention period to ``days``.
  You can specify if you want to ``copy-tags`` from the DB instance to the snapshot, default is False
