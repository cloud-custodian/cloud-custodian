Load Balancer - Network Tiers
=============================

These examples allow to work with GCP loadbalancer-address resource. It described below how to notify to Cloud Pub/Sub information about the addresses in standard and premium tiers.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
        - name: load-balancers-addresses-in-standard-network-tier
          description: |
            List of Load Balancers' Addresses in standard network tier
          resource: gcp.loadbalancer-address
          filters:
            - type: value
              key: networkTier
              value: STANDARD
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources
        - name: load-balancers-addresses-in-premium-network-tier
          description: |
            List of Load Balancers' Addresses in premium network tier
          resource: gcp.loadbalancer-address
          filters:
            - type: value
              key: networkTier
              value: PREMIUM
          actions:
            - type: notify
              to:
                - email@email
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/load-balancer-resources
