Resource Manager - Template 1
==============================

TBD {description of the example}

Details about all available Resource Manager resources are available at the :ref:`gcp_resourcemanager` page.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
        - name: {name}
          description: |
            {description}
          resource: gcp.{resource}
          filters:
            - type:
              key:
              value:
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/deployment-manager