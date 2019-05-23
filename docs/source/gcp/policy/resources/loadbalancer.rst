.. _gcp_loadbalancer:

Load Balancer
=============

Filters
--------
 - Standard Value Filter (see :ref:`filters`)
    Fields for filtering can be received from GCP resource object. Link to appropriate resource is
    provided in each GCP resource.

Actions
--------
 - GCP Actions (see :ref:`gcp_genericgcpactions`)

Example Policies
----------------

Load Balancer. Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Addresses <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Global Addresses
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Global Addresses <https://cloud.google.com/compute/docs/reference/rest/v1/globalAddresses>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. URL Maps
~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: URL Maps <https://cloud.google.com/compute/docs/reference/rest/v1/urlMaps>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Target HTTP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Target HTTP Proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpProxies>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. HTTPs Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: HTTPs Proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetHttpsProxies>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Target TCP Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Target TCP Proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetTcpProxies>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Target SSL Proxies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Target SSL Proxies <https://cloud.google.com/compute/docs/reference/rest/v1/targetSslProxies>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. SSL Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: SSL Policies <https://cloud.google.com/compute/docs/reference/rest/v1/sslPolicies>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. SSL Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: SSL Certificates <https://cloud.google.com/compute/docs/reference/rest/v1/sslCertificates>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Backend Buckets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Backend Buckets <https://cloud.google.com/compute/docs/reference/rest/v1/backendBuckets>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Health Checks <https://cloud.google.com/compute/docs/reference/rest/v1/healthChecks>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. HTTP Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: HTTP Health Checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpHealthChecks>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. HTTPs Health Checks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: HTTPs Health Checks <https://cloud.google.com/compute/docs/reference/rest/v1/httpsHealthChecks>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Target Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Target Instances <https://cloud.google.com/compute/docs/reference/rest/v1/targetInstances>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Target Pools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Target Pools <https://cloud.google.com/compute/docs/reference/rest/v1/targetPools>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Forwarding Rules <https://cloud.google.com/compute/docs/reference/rest/v1/addresses>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Global Forwarding Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Global Forwarding Rules <https://cloud.google.com/compute/docs/reference/rest/v1/forwardingRules>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Backend Services <https://cloud.google.com/compute/docs/reference/rest/v1/backendServices>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer

Load Balancer. Region Backend Services
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Region Backend Services <https://cloud.google.com/compute/docs/reference/rest/v1/regionBackendServices>`_

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
                topic: projects/cloud-custodian/topics/loadbalancer
