.. _elb:

Elastic Load Balancers (ELB)
============================

Filters
-------

- Standard Value Filter (see :ref:`filters`)

``is-ssl``
  Check if ELB is using SSL

  .. c7n-schema:: IsSSLFilter
      :module: c7n.resources.elb

``ssl-policy``
  Filter on SSL Policy, supports whitelists and blacklists

  .. c7n-schema:: SSLPolicyFilter
      :module: c7n.resources.elb

``healthcheck-protocol-mismatch``
  Check if any of the protocols in the ELB match the health check

  .. c7n-schema:: HealthCheckProtocolMismatch
      :module: c7n.resources.elb

Actions
-------

``delete``
  Delete ELB

  .. c7n-schema:: Delete
      :module: c7n.resources.elb

``set-ssl-listener-policy``
  Set SSL listener policy

  .. c7n-schema:: SetSslListenerPolicy
      :module: c7n.resources.elb
