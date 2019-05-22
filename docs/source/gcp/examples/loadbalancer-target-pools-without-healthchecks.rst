Load Balancer - Target pools without health checks
===================================================

This example uses GCP loadbalancer-target-pool resource. The example shows how to notify to Cloud Pub/Sub information about age of SSL certificates.

Details about all available load-balancer resources are available at the :ref:`gcp_loadbalancer` page.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
      - name: gcp-loadbalancer-target-pool-no-healthcheks-notify
        description: |
          Load target pools without health checks
        resource: gcp.loadbalancer-target-pool
        filters:
        - type: value
          key: healthChecks
          op: eq
          value: null
        actions:
        - type: notify
          subject: Health checks are absent
          to:
          - email@address
          format: json
          transport:
            type: pubsub
            topic: projects/cloud-custodian/topics/loadbalancer
