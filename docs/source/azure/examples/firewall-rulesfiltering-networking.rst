Firewall - Filter Storage Accounts By Rules
============================================

This example demonstrates a common filtering scenario where we would
like to ensure all firewalls are configured to only allow access from
IP addresses in our datacenter (or any block of IP space).

Below we look at storage accounts and we identify any accounts where
the firewall is not enabled *or* the firewall is enabled but it allows
IP's that are not within the specified IP space.

The IP space is specified as an array and can contain a variety of formats
as shown in the example.

The ``only`` field used in the firewall rules filter returns any resources
where the firewall **only** contains IP's from the list provided.  It need
not contain all of them (or any of them).  In this example we use the ``not``
modifier to find non-compliant resources.

You could further extend this example by using the ``set-network-rules`` action
to remediate the non-compliant resources.

.. code-block:: yaml

    policies:
      - name: storage-only-allow-datacenter-ips
        description: |
          Find all storage accounts which permit access
          from any IP not in datacenter IP space
        resource: azure.storage
        filters:
          - or:
            - type: value
              key: properties.networkAcls.defaultAction
              value: 'Allow'

            - not:
              - type: firewall-rules
                only:
                  - '8.8.8.8'
                  - '10.0.0.0/16'
                  - '20.0.0.0 - 20.10.0.0'


