.. _gcp_loadbalancer:

Load Balancer
=============

Filters
--------
 - Standard Value Filter (see :ref:`filters`)

Actions
--------
 - GCP Actions (see :ref:`gcp_genericgcpactions`)

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
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-addresses
          description: |
            List of Load Balancers' Addresses
          resource: gcp.loadbalancer-address
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Global Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `global addresses <https://cloud.google.com/compute/docs/reference/rest/v1/globalAddresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-addresses
          description: |
            List of Load Balancers' Global Addresses
          resource: gcp.loadbalancer-global-address
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' URL Maps
~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `URL maps <https://cloud.google.com/compute/docs/reference/rest/v1/urlMaps>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-url-maps
          description: |
            List of Load Balancers' Url Maps
          resource: gcp.loadbalancer-url-map
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Target HTTP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-http-proxies
          description: |
            List of Load Balancers' Target HTTP Proxies
          resource: gcp.loadbalancer-target-http-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' HTTPs Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTPs proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpsProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-https-proxies
          description: |
            List of Load Balancers' HTTPs Proxies
          resource: gcp.loadbalancer-target-https-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Target TCP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target TCP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetTcpProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-tcp-proxies
          description: |
            List of Load Balancers' Target TCP Proxies
          resource: gcp.loadbalancer-target-tcp-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Target SSL Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target SSL proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetSslProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-ssl-proxies
          description: |
            List of Load Balancers' Target SSL Proxies
          resource: gcp.loadbalancer-target-ssl-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' SSL Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL policies <https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-policies
          description: |
            List of Load Balancers' SSL Policies
          resource: gcp.loadbalancer-ssl-policy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' SSL Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL certificates <https://cloud.google.com/compute/docs/reference/rest/v1/sslCertificates>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-certificates
          description: |
            List of Load Balancers' SSL Certificates
          resource: gcp.loadbalancer-ssl-certificate
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Backend Buckets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend buckets <https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-buckets
          description: |
            List of Load Balancers' Backend Buckets
          resource: gcp.loadbalancer-backend-bucket
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `health checks <https://cloud.google.com/compute/docs/reference/rest/v1/healthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-health-checks
          description: |
            List of Load Balancers' Health Checks
          resource: gcp.loadbalancer-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' HTTP Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTP health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpHealthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-http-health-checks
          description: |
            Load Balancers' HTTP Health Checks
          resource: gcp.loadbalancer-http-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' HTTPs Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTPs health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpsHealthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-https-health-checks
          description: |
            List of Load Balancers' HTTPs Health Checks
          resource: gcp.loadbalancer-https-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Target Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target instances <https://cloud.google.com/compute/docs/reference/rest/v1/targetInstances>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-instances
          description: |
            List of Load Balancers' Target Instances
          resource: gcp.loadbalancer-target-instance
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Target Pools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target pools <https://cloud.google.com/compute/docs/reference/rest/v1/targetPools>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-pools
          description: |
            List of Load Balancers' Target Pools
          resource: gcp.loadbalancer-target-pool
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-forwarding-rules
          description: |
            List of Load Balancers' Forwarding Rules
          resource: gcp.loadbalancer-forwarding-rule
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Global Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `forwarding rules <https://cloud.google.com/compute/docs/reference/rest/v1/forwardingRules>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-forwarding-rules
          description: |
            List of Load Balancers' Global Forwarding Rules
          resource: gcp.loadbalancer-global-forwarding-rule
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend services <https://cloud.google.com/compute/docs/reference/rest/v1/backendServices>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-services
          description: |
            List of Load Balancers' Backend Services
          resource: gcp.loadbalancer-backend-service
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancers' Region Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `region backend services <https://cloud.google.com/compute/docs/reference/rest/v1/regionBackendServices>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

The 'region' param in the query is required.

.. code-block:: yaml

    policies:
        - name: load-balancers-region-backend-services
          description: |
            List of Load Balancers' Region Backend Services
          resource: gcp.loadbalancer-region-backend-service
          query:
            - region: us-central1
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources
