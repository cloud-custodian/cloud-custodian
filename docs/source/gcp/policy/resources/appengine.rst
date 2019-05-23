.. _gcp_appengine:

App Engine
===========

Filters
--------
 - Standard Value Filter (see :ref:`filters`)

Actions
--------
 - GCP Actions (see :ref:`gcp_genericgcpactions`)

Example Policies
----------------

App Engine. Apps
~~~~~~~~~~~~~~~~
The resource works with `apps <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

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
The resource works with `authorized certificates <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedCertificates>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

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
The resource works with `authorized domains <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedDomains>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

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
The resource works with `domain mappings <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.domainMappings>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

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
The resource works with `ingress rules of apps' firewall <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.firewall.ingressRules>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

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
