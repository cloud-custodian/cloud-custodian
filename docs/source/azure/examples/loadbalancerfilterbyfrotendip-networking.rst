Load Balancer - Filter load balancer by front end public ip
===========================================================

Filter to select load balancers with an ipv6 frontend public IP.

.. code-block:: yaml

    policies:
       - name: loadbalancer-with-ipv6-frontend
         resource: azure.loadbalancer
         filters:
            - type: frontend-public-ip
              key: properties.publicIPAddressVersion
              op: in
              value_type: normalize
              value: "ipv6"
