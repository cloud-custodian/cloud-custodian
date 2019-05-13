.. _gcp_loadbalancer:

Load Balancer
=============

Filters: TBD
------------
Filters are not implemented.

Actions: TBD
------------
Actions are not implemented.

Environment variables
---------------------
To check the policies please make sure that following environment variables are set:

- GOOGLE_CLOUD_PROJECT

- GOOGLE_APPLICATION_CREDENTIALS

The details about the variables are available in the `GCP documentation to configure credentials for service accounts. <https://cloud.google.com/docs/authentication/getting-started>`_

Example Policies
----------------

Load Balancers' Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-addresses
          description: |
            List of Load Balancers' Addresses
          resource: gcp.loadbalancer-address

Load Balancers' Global Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `global addresses <https://cloud.google.com/compute/docs/reference/rest/v1/globalAddresses>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-addresses
          description: |
            List of Load Balancers' Global Addresses
          resource: gcp.loadbalancer-global-address

Load Balancers' URL Maps
~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `URL maps <https://cloud.google.com/compute/docs/reference/rest/v1/urlMaps>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-url-maps
          description: |
            List of Load Balancers' Url Maps
          resource: gcp.loadbalancer-url-map

Load Balancers' Target HTTP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpProxies>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-http-proxies
          description: |
            List of Load Balancers' Target HTTP Proxies
          resource: gcp.loadbalancer-target-http-proxy

Load Balancers' HTTPs Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTPs proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpsProxies>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-https-proxies
          description: |
            List of Load Balancers' HTTPs Proxies
          resource: gcp.loadbalancer-target-https-proxy

Load Balancers' Target TCP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target TCP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetTcpProxies>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-tcp-proxies
          description: |
            List of Load Balancers' Target TCP Proxies
          resource: gcp.loadbalancer-target-tcp-proxy

Load Balancers' Target SSL Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target SSL proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetSslProxies>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-ssl-proxies
          description: |
            List of Load Balancers' Target SSL Proxies
          resource: gcp.loadbalancer-target-ssl-proxy

Load Balancers' SSL Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL policies <https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-policies
          description: |
            List of Load Balancers' SSL Policies
          resource: gcp.loadbalancer-ssl-policy

Load Balancers' SSL Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL certificates <https://cloud.google.com/compute/docs/reference/rest/v1/sslCertificates>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-certificates
          description: |
            List of Load Balancers' SSL Certificates
          resource: gcp.loadbalancer-ssl-certificate

Load Balancers' Backend Buckets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend buckets <https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-buckets
          description: |
            List of Load Balancers' Backend Buckets
          resource: gcp.loadbalancer-backend-bucket

Load Balancers' Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `health checks <https://cloud.google.com/compute/docs/reference/rest/v1/healthChecks>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-health-checks
          description: |
            List of Load Balancers' Health Checks
          resource: gcp.loadbalancer-health-check

Load Balancers' HTTP Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTP health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpHealthChecks>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-http-health-checks
          description: |
            Load Balancers' HTTP Health Checks
          resource: gcp.loadbalancer-http-health-check

Load Balancers' HTTPs Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTPs health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpsHealthChecks>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-https-health-checks
          description: |
            List of Load Balancers' HTTPs Health Checks
          resource: gcp.loadbalancer-https-health-check

Load Balancers' Target Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target instances <https://cloud.google.com/compute/docs/reference/rest/v1/targetInstances>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-instances
          description: |
            List of Load Balancers' Target Instances
          resource: gcp.loadbalancer-target-instance

Load Balancers' Target Pools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target pools <https://cloud.google.com/compute/docs/reference/rest/v1/targetPools>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-pools
          description: |
            List of Load Balancers' Target Pools
          resource: gcp.loadbalancer-target-pool

Load Balancers' Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-forwarding-rules
          description: |
            List of Load Balancers' Forwarding Rules
          resource: gcp.loadbalancer-forwarding-rule

Load Balancers' Global Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `forwarding rules <https://cloud.google.com/compute/docs/reference/rest/v1/forwardingRules>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-forwarding-rules
          description: |
            List of Load Balancers' Global Forwarding Rules
          resource: gcp.loadbalancer-global-forwarding-rule

Load Balancers' Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend services <https://cloud.google.com/compute/docs/reference/rest/v1/backendServices>`_ GCP REST resource.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-services
          description: |
            List of Load Balancers' Backend Services
          resource: gcp.loadbalancer-backend-service

Load Balancers' Region Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `region backend services <https://cloud.google.com/compute/docs/reference/rest/v1/regionBackendServices>`_ GCP REST resource.

The 'region' param in the query is required.

.. code-block:: yaml

    policies:
        - name: load-balancers-region-backend-services
          description: |
            List of Load Balancers' Region Backend Services
          resource: gcp.loadbalancer-region-backend-service
          query:
            - region: us-central1
