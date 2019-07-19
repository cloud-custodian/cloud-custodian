Load Balancer - Filter load balancer by front end public ip
===========================================================

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
