.. _gcp_loadbalancer:

Load Balancer
=============

Filters
--------
 - Standard Value Filter (see :ref:`filters`)

Actions
--------
 - GCP Actions (see :ref:`gcp_genericgcpactions`)

Example Policies
----------------

Load Balancer. Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-addresses
          description: |
            Load Balancer. List of Addresses
          resource: gcp.loadbalancer-address
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Global Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `global addresses <https://cloud.google.com/compute/docs/reference/rest/v1/globalAddresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-addresses
          description: |
            Load Balancer. List of Global Addresses
          resource: gcp.loadbalancer-global-address
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. URL Maps
~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `URL maps <https://cloud.google.com/compute/docs/reference/rest/v1/urlMaps>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-url-maps
          description: |
            Load Balancer. List of Url Maps
          resource: gcp.loadbalancer-url-map
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Target HTTP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-http-proxies
          description: |
            Load Balancer. List of Target HTTP Proxies
          resource: gcp.loadbalancer-target-http-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. HTTPs Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target HTTPs proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpsProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-https-proxies
          description: |
            Load Balancer. List of HTTPs Proxies
          resource: gcp.loadbalancer-target-https-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Target TCP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target TCP proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetTcpProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-tcp-proxies
          description: |
            Load Balancer. List of Target TCP Proxies
          resource: gcp.loadbalancer-target-tcp-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Target SSL Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target SSL proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetSslProxies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-ssl-proxies
          description: |
            Load Balancer. List of Target SSL Proxies
          resource: gcp.loadbalancer-target-ssl-proxy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. SSL Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL policies <https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-policies
          description: |
            Load Balancer. List of SSL Policies
          resource: gcp.loadbalancer-ssl-policy
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. SSL Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `SSL certificates <https://cloud.google.com/compute/docs/reference/rest/v1/sslCertificates>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-ssl-certificates
          description: |
            Load Balancer. List of SSL Certificates
          resource: gcp.loadbalancer-ssl-certificate
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Backend Buckets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend buckets <https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-buckets
          description: |
            Load Balancer. List of Backend Buckets
          resource: gcp.loadbalancer-backend-bucket
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `health checks <https://cloud.google.com/compute/docs/reference/rest/v1/healthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-health-checks
          description: |
            Load Balancer. List of Health Checks
          resource: gcp.loadbalancer-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. HTTP Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTP health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpHealthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-http-health-checks
          description: |
            Load Balancer. HTTP Health Checks
          resource: gcp.loadbalancer-http-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. HTTPs Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `HTTPs health checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpsHealthChecks>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-https-health-checks
          description: |
            Load Balancer. List of HTTPs Health Checks
          resource: gcp.loadbalancer-https-health-check
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Target Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target instances <https://cloud.google.com/compute/docs/reference/rest/v1/targetInstances>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-instances
          description: |
            Load Balancer. List of Target Instances
          resource: gcp.loadbalancer-target-instance
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Target Pools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `target pools <https://cloud.google.com/compute/docs/reference/rest/v1/targetPools>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-target-pools
          description: |
            Load Balancer. List of Target Pools
          resource: gcp.loadbalancer-target-pool
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-forwarding-rules
          description: |
            Load Balancer. List of Forwarding Rules
          resource: gcp.loadbalancer-forwarding-rule
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Global Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `forwarding rules <https://cloud.google.com/compute/docs/reference/rest/v1/forwardingRules>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-global-forwarding-rules
          description: |
            Load Balancer. List of Global Forwarding Rules
          resource: gcp.loadbalancer-global-forwarding-rule
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `backend services <https://cloud.google.com/compute/docs/reference/rest/v1/backendServices>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: load-balancers-backend-services
          description: |
            Load Balancer. List of Backend Services
          resource: gcp.loadbalancer-backend-service
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources

Load Balancer. Region Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `region backend services <https://cloud.google.com/compute/docs/reference/rest/v1/regionBackendServices>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

The 'region' param in the query is required.

.. code-block:: yaml

    policies:
        - name: load-balancers-region-backend-services
          description: |
            Load Balancer. List of Region Backend Services
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
