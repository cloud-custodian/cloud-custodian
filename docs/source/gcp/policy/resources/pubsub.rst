.. _gcp_pubsub:

Pub/Sub
=======

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

Pub/Sub. Topics
~~~~~~~~~~~~~~~
`GCP resource: Topics <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics>`_

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
`GCP resource: Subscriptions <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.subscriptions>`_

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
`GCP resource: Snapshots <https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.snapshots>`_

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
