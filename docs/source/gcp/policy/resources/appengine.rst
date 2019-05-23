.. _gcp_appengine:

App Engine
===========

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

App Engine. Apps
~~~~~~~~~~~~~~~~
`GCP resource: Apps <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps>`_ 

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-apps
          description: |
            App Engine. List of apps
          resource: gcp.app-engine
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine

App Engine. Authorized Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Authorized Certificates <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedCertificates>`_ 

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-authorized-certificates-notify
          description: |
            App Engine. List of authorized certificates
          resource: gcp.app-engine-certificate
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine

App Engine. Authorized Domains
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Authorized Domains <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedDomains>`_ 

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-authorized-domains-notify
          description: |
            App Engine. List of authorized domains
          resource: gcp.app-engine-domain
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine

App Engine. Domain Mappings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Domain Mappings <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.domainMappings>`_ 

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-domain-mappings-notify
          description: |
            App Engine. List of Domain Mappings
          resource: gcp.app-engine-domain-mapping
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine

App Engine. Apps Firewall Ingress Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
`GCP resource: Ingress Rules of Apps' firewall <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.firewall.ingressRules>`_ 

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-apps-firewall-ingress-rules-notify
          description: |
            App Engine. List of Apps' Firewall Ingress Rules
          resource: gcp.app-engine-firewall-ingress-rule
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine
