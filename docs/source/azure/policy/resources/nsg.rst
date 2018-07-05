.. _azure_nsg:

Network Security Groups
=======================

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `NetworkSecurityGroup <https://docs.microsoft.com/en-us/python/api/azure.mgmt.network.v2018_02_01.models.networksecuritygroup?view=azure-python>`_
- ARM Resource Filters (see :ref:`azure_genericarmfilter`)
    - Metric Filter - Filter on metrics from Azure Monitor
    - Tag Filter - Filter on tag presence and/or values
    - Marked-For-Op Filter - Filter on tag that indicates a scheduled operation for a resource
- ``ingress``
  Filter based on Inbound Security Rules

  .. c7n-schema:: IngressFilter
      :module: c7n_azure.resources.network_security_group

- ``egress``
  Filter based on Outbound Security Rules

  .. c7n-schema:: EgressFilter
      :module: c7n_azure.resources.network_security_group


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)
- ``open``
  Allow access to security rules

  .. c7n-schema:: CloseRules
      :module: c7n_azure.resources.network_security_group

- ``close``
  Deny access to security rules

  .. c7n-schema:: OpenRules
      :module: c7n_azure.resources.network_security_group


Example Policies
----------------

This policy will deny access to all security rules with Inbound SSH ports in the range [8080,8090]

.. code-block:: yaml

     policies:
       - name: close-ingress-8080-8090
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            fromPort: 8080
            toPort: 8090
         actions:
          - type: close

This policy will deny access to all security rules with any Inbound SSH ports that are NOT 22, 23 or 24

.. code-block:: yaml

     policies:
       - name: close-ingress-except-22-24
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            exceptPorts: [22,23,24]
         actions:
          - type: close

This policy will deny access to all security rules with any Outbound SSH ports with a TCP Protocol

.. code-block:: yaml

     policies:
       - name: close-egress-except-TCP
         resource: azure.networksecuritygroup
         filters:
          - type: egress
            ipProtocol: TCP
         actions:
          - type: close