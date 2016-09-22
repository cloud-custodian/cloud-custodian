.. _elb:

Elastic Load Balancers (ELB)
============================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``is-ssl``
  Check if ELB is using SSL

``ssl-policy``
  Filter on SSL Policy, supports whitelists and blacklists

``healthcheck-protocol-mismatch``
  Check if any of the protocols in the ELB match the health check

Actions
-------

``delete``
  Delete ELB

``set-ssl-listener-policy``
  Set SSL listener policy
