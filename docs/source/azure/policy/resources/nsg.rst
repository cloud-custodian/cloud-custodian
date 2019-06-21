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
- ``ingress`` Filter based on Inbound Security Rules
    - `ports`: ports to include (`0-65535` if not specified)
        - `80`, `80-100`, `80,90-100`
    - `exceptPorts`: ports to ignore (empty if not specified)
    - `match`: match operation, filter includes NSGs with all or at least one port from the list.
        -Possible values: `any`, `all`
    - `ipProtocol`: `TCP`, `UDP` or `*`. Default: `*`
    - `access`: `Allow`, `Deny`

  .. c7n-schema:: azure.networksecuritygroup.filters.ingress

- ``egress`` Filter based on Outbound Security Rules
    - `ports`: ports to include (`0-65535` if not specified)
        - `80`, `80-100`, `80,90-100`
    - `exceptPorts`: ports to ignore (empty if not specified)
    - `match`: match operation, filter includes NSGs with all or at least one port from the list.
        -Possible values: `any`, `all`
    - `ipProtocol`: `TCP`, `UDP` or `*`. Default: `*`
    - `access`: `Allow`, `Deny`

  .. c7n-schema:: azure.networksecuritygroup.filters.egress


Actions
-------
- ARM Resource Actions (see :ref:`azure_genericarmaction`)
- ``open`` Allow access to security rules
    - `ports`: ports to include (`0-65535` if not specified)
        - `80`, `80-100`, `80,90-100`
    - `exceptPorts`: ports to ignore (empty if not specified)
    - `ipProtocol`: `TCP`, `UDP` or `*`. Default: `*`
    - `direction`: `Inbound`, `Outbound`
    - `access`: `Allow`, `Deny`

  .. c7n-schema:: azure.networksecuritygroup.actions.open

- ``close`` Deny access to security rules
    - `ports`: ports to include (`0-65535` if not specified)
        - `80`, `80-100`, `80,90-100`
    - `exceptPorts`: ports to ignore (empty if not specified)
    - `ipProtocol`: `TCP`, `UDP` or `*`. Default: `*`
    - `direction`: `Inbound`, `Outbound`
    - `access`: `Allow`, `Deny`

  .. c7n-schema:: azure.networksecuritygroup.actions.close


Example Policies
----------------

This policy will deny access to all ports that are NOT 22, 23 or 24 for all Network Security Groups

.. code-block:: yaml

      policies:
       - name: close-inbound-except-22-24
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            exceptPorts: '22-24'
            ports-op: 'any'
            access: 'Allow'
         actions:
          - type: close
            exceptPorts: '22-24'
            direction: 'Inbound'

This policy will find all NSGs with port 80 opened and port 443 closed, then it will open port 443

.. code-block:: yaml

     policies:
       - name: close-egress-except-TCP
         resource: azure.networksecuritygroup
         filters:
          - type: ingress
            ports: '80'
            access: 'Allow'
          - type: ingress
            ports: '443'
            access: 'Deny'
         actions:
          - type: open
            ports: '443'
