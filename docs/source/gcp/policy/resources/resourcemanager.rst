.. _gcp_resourcemanager:

Resource Manager
=================

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

Resource Manager. Organizations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The resource works with `organizations <https://cloud.google.com/resource-manager/reference/rest/v1/organizations>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: gcp-rm-organizations-notify
          description: |
            Resource Manager. List of organizations
          resource: gcp.organization
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/resource-manager