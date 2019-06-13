.. _ebs:

Elastic Block Store Volumes (EBS Volumes)
=========================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``instance``
  Filter volumes based on filtering on their attached instance

  .. c7n-schema:: aws.ebs.filters.instance


Actions
-------

``delete``
  Delete volume

  .. c7n-schema:: aws.ebs.actions.delete


``copy-instance-tags``
  Copy instance tags to its attached volume.

  .. c7n-schema:: aws.ebs.actions.copy-instance-tags


``encrypt-instance-volumes``
  Encrypt extant volumes attached to an instance
  (see :py:class:`c7n.resources.ebs.EncryptInstanceVolumes`)

  .. c7n-schema:: aws.ebs.actions.encrypt-instance-volumes

