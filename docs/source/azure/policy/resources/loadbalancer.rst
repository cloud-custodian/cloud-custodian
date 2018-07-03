.. _azure_loadbalancer:

Load Balancer
=============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `LoadBalancer <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2017_11_01.models.loadbalancer?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
- ``frontend-public-ip``
  Filters load balancers by the frontend public IP
  .. c7n-schema:: FrontEndIp
      :module: c7n_azure.resources.load_balancer

Actions
-------

- ARM Resource Actions (see :ref:`azure_genericarmaction`)

Example Policies
----------------

This policy will filter load balancers with an ipv6 frontend public IP

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
