.. _ebs:

Elastic Block Store Volumes (EBS Volumes)
=========================================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``instance``
  Filter volumes based on filtering on their attached instance

  .. c7n-schema:: AttachedInstanceFilter
      :module: c7n.resources.ebs

Actions
-------

``delete``
  Delete volume

  .. c7n-schema:: Delete
      :module: c7n.resources.ebs

``copy-instance-tags``
  Copy instance tags to its attached volume.

  .. c7n-schema:: CopyInstanceTags
      :module: c7n.resources.ebs

``encrypt-instance-volumes``
  Encrypt extant volumes attached to an instance
  (see :py:class:`c7n.resources.ebs.EncryptInstanceVolumes`)

  .. c7n-schema:: EncryptInstanceVolumes
      :module: c7n.resources.ebs
