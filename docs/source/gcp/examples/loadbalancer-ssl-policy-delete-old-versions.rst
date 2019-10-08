Load Balancer - SSL Policies - Delete policies by TLS version
==============================================================

It's possible to delete all SSL Policies that don't have TLS version 1.2.

.. code-block:: yaml

    policies:
      - name: gcp-load-balancing-ssl-policies-delete
        resource: gcp.loadbalancer-ssl-policy
        filters:
          - type: value
            key: minTlsVersion
            op: ne
            value: TLS_1_2
        actions:
          - type: delete