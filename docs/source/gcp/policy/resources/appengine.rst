.. _gcp_appengine:

App Engine
==========

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

App Engine Apps
~~~~~~~~~~~~~~~~
The resource works with `apps <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: appengine-apps
          description: |
            Description
          resource: gcp.loadbalancer-address
          actions:
            - type: notify
              to:
                - Pub\Sub
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine

App Engine Authorized Certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `authorized certificates <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1/apps.authorizedCertificates>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: gcp-app-engine-certificate-notify
          description: |
            Notify about App Engine certificates
          resource: gcp.app-engine-certificate
          actions:
            - type: notify
              to:
                - Pub\Sub
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/appengine