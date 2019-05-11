.. _gcp_loadbalancer:

Load Balancer
=============

Filters: TBD
------------

Actions: TBD
------------

TBD: information about environment variables

Example Policies
----------------

Load Balancers' Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-addresses
          description: |
            List of Load Balancers' Addresses
          resource: gcp.loadbalancer-address

Load Balancers' Global Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-global-addresses
          description: |
            List of Load Balancers' Global Addresses
          resource: gcp.loadbalancer-global-address

Load Balancers' URL Maps
~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-url-maps
          description: |
            List of Load Balancers' Url Maps
          resource: gcp.loadbalancer-url-map

Load Balancers' Target HTTP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-http-proxies
          description: |
            List of Load Balancers' Target HTTP Proxies
          resource: gcp.loadbalancer-target-http-proxy

Load Balancers' HTTPs Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-https-proxies
          description: |
            List of Load Balancers' HTTPs Proxies
          resource: gcp.loadbalancer-target-https-proxy

Load Balancers' Target TCP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-tcp-proxies
          description: |
            List of Load Balancers' Target TCP Proxies
          resource: gcp.loadbalancer-target-tcp-proxy

Load Balancers' Target SSL Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-ssl-proxies
          description: |
            List of Load Balancers' Target SSL Proxies
          resource: gcp.loadbalancer-target-ssl-proxy

Load Balancers' SSL Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-policies
          description: |
            List of Load Balancers' SSL Policies
          resource: gcp.loadbalancer-ssl-policy

Load Balancers' SSL Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-certificates
          description: |
            List of Load Balancers' SSL Certificates
          resource: gcp.loadbalancer-ssl-certificate

Load Balancers' Backend Buckets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-backend-buckets
          description: |
            List of Load Balancers' Backend Buckets
          resource: gcp.loadbalancer-backend-bucket

Load Balancers' Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-health-checks
          description: |
            List of Load Balancers' Health Checks
          resource: gcp.loadbalancer-health-check

Load Balancers' HTTP Health Check
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-http-health-checks
          description: |
            Load Balancers' HTTP Health Checks
          resource: gcp.loadbalancer-http-health-check

Load Balancers' HTTPs Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-https-health-checks
          description: |
            List of Load Balancers' HTTPs Health Checks
          resource: gcp.loadbalancer-https-health-check

Load Balancers' Target Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-instances
          description: |
            List of Load Balancers' Target Instances
          resource: gcp.loadbalancer-target-instance

Load Balancers' Target Pools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-target-pools
          description: |
            List of Load Balancers' Target Pools
          resource: gcp.loadbalancer-target-pool

Load Balancers' Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-forwarding-rules
          description: |
            List of Load Balancers' Forwarding Rules
          resource: gcp.loadbalancer-forwarding-rule

Load Balancers' Global Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-global-forwarding-rules
          description: |
            List of Load Balancers' Global Forwarding Rules
          resource: gcp.loadbalancer-global-forwarding-rule

Load Balancers' Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-backend-services
          description: |
            List of Load Balancers' Backend Services
          resource: gcp.loadbalancer-backend-service

Load Balancers' Region Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: yaml

    policies:
        - name: load-balancers-region-backend-services
          description: |
            List of Load Balancers' Region Backend Services
          resource: gcp.loadbalancer-region-backend-service
          query:
            - region: us-central1
