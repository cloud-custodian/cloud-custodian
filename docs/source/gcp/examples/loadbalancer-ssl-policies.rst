Load Balancer - SSL Policies
=============================

The example uses GCP loadbalancer-ssl-policy resource. It described below how to notify to Cloud Pub/Sub information about the policies with CUSTOM profile.

Details about all available load-balancer resources are available at the :ref:`gcp_loadbalancer` page.

To configure Cloud Pub/Sub messaging please take a look at the :ref:`gcp_genericgcpactions` page.

.. code-block:: yaml

    policies:
        - name: load-balancers-custom-ssl-policies-notify
          description: |
            Load Balancer. SSL policies with CUSTOM profile
          resource: gcp.loadbalancer-ssl-policy
          filters:
            - type: value
              key: profile
              value: CUSTOM
          actions:
            - type: notify
              to:
                - email@address
              format: json
              transport:
                type: pubsub
                topic: projects/cloud-custodian/topics/loadbalancer
