Load Balancer - SSL certificates age
=====================================

This example uses GCP loadbalancer-ssl-certificate resource. The example shows how to notify to Cloud Pub/Sub information about age of SSL certificates.

Details about all available load-balancer resources are available at the :ref:`gcp_loadbalancer` page.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
      - name: gcp-loadbalancer-certificates-age
        description: |
          Check the existing certificates age greater than 300 days
        resource: gcp.loadbalancer-ssl-certificate
        filters:
        - type: value
          key: creationTimestamp
          op: greater-than
          value_type: age
          value: 300
        actions:
        - type: notify
          subject: Certificates ages greater than 300 days
          to:
          - email@address
          format: json
          transport:
            type: pubsub
            topic: projects/cloud-custodian/topics/loadbalancer
