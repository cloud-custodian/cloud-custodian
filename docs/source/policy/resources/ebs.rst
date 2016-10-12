.. _ebs:

Elastic Block Store Volumes (EBS Volumes)
=========================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``instance``
  Filter volumes based on filtering on their attached instance

Actions
-------

``delete``
  Delete CloudFormation Stack

``copy-instance-tags``
  Copy instance tags to its attached volume.

``encrypt-instance-volumes``
  Encrypt extant volumes attached to an instance
  (see :py:class:`c7n.resources.ebs.EncryptInstanceVolumes`)
