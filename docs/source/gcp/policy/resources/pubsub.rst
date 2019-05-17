.. _gcp_pubsub:

Pub/Sub
=======

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

Pub/Sub. Topics
~~~~~~~~~~~~~~~
The resource works with `topics <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: gcp-pub-sub-topics-notify
          description: |
            Pub\Sub. List of topics
          resource: gcp.pubsub-topic
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/pubsub

Pub/Sub. Subscriptions
~~~~~~~~~~~~~~~~~~~~~~
The resource works with `subscriptions <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: gcp-pub-sub-subscriptions-notify
          description: |
            Pub\Sub. List of subscriptions
          resource: gcp.pubsub-subscription
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/pubsub

Pub/Sub. Snapshots
~~~~~~~~~~~~~~~~~~
The resource works with `snapshots <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.snapshots>`_ GCP REST resource. Fields that are provided by the REST resource can be used in the policy filter.

.. code-block:: yaml

    policies:
        - name: gcp-pub-sub-snapshots-notify
          description: |
            Pub\Sub. List of snapshots
          resource: gcp.pubsub-snapshot
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/pubsub
