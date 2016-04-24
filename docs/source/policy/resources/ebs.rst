.. _ebs:

Elastic Block Stores (EBS)
==========================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``age``
  Based on ``StartTime`` of volume in Days

``instance``
  Filter volumes based on filtering on their attached instance

Actions
-------

``delete`` (Volumes)
  Delete CloudFormation Stack

``delete`` (Snapshots)
  Delete EBS Snapshot based on ``skip-ami-snapshots``

``copy-instance-tags``
  Copy instance tags to its attached volume.

``encrypt-instance-volumes``
  Encrypt extant volumes attached to an instance
  (see :py:class:`c7n.resources.ebs.EncryptInstanceVolumes`)
