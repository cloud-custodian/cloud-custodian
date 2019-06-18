.. _elb:

Elastic Load Balancers (ELB)
============================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``is-ssl``
  Check if ELB is using SSL

  .. c7n-schema:: aws.elb.filters.is-ssl


``ssl-policy``
  Filter on SSL Policy, supports whitelists and blacklists

  .. c7n-schema:: aws.elb.filters.ssl-policy


``healthcheck-protocol-mismatch``
  Check if any of the protocols in the ELB match the health check

  .. c7n-schema:: aws.elb.filters.healthcheck-protocol-mismatch


Actions
-------

``delete``
  Delete ELB

  .. c7n-schema:: aws.elb.actions.delete


``set-ssl-listener-policy``
  Set SSL listener policy

  .. c7n-schema:: aws.elb.actions.set-ssl-listener-policy

