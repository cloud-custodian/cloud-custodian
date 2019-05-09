.. _redshift:

Redshift
========

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``param``
  Checks the ``ClusterParameterGroups`` for Redshift resource

  .. c7n-schema:: Parameter
      :module: c7n.resources.redshift

Actions
-------

``delete``
  Delete Redshift resource and you can specify if you want to ``skip-snapshot``, default is False

  .. c7n-schema:: Delete
      :module: c7n.resources.redshift
