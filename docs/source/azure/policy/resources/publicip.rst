.. _azure_public_ip:

Public IP Addresses
===================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
- Arm Filters (see :ref:`azure_genericarmfilter`)

``metric``
  Filter based on metrics from Azure Monitor, such as TCPBytesInDDoS, UDPBytesDroppedDDos, etc.

  .. c7n-schema:: MetricFilter
       :module: c7n_azure.filters

Actions
-------

``delete``
  Delete the Public IP Address

  .. c7n-schema:: PublicIPDeleteAction
       :module: c7n_azure.resources.public_ip

Example Policies
----------------

Delete specific public IP

.. code-block:: yaml

    policies:
      - name: delete-public-ip
        resource: azure.publicip
        filters:
          - type: value
            key: name
            value: fake-ip-name
        actions:
          - type: delete
