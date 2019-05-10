.. _kms:

Key Management Service (KMS)
============================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``grant-count``
  Call ``list_grants`` and count ``Grants`` for each ``TargetKeyId``

  .. c7n-schema:: GrantCount
      :module: c7n.resources.kms

Actions
-------

No actions for KMS at this time. The KMS resource can only be used for reporting,
so KMS policies do not have an Action section.
