.. _ami:

Amazon Machine Images (AMI)
===========================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``image-age``
  Checks the ``CreationDate`` of the AMI. Age is in days.
  **Deprecated** use value filter with `value_type: age`

  .. c7n-schema:: aws.ami.filters.image-age


Actions
-------

``deregister``
  Deregisters the specified AMI. After you deregister an AMI, it can't be used to launch new instances. This command does not delete the AMI.

  .. c7n-schema:: aws.ami.actions.deregister

