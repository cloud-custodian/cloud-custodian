Cloud SQL - Notify on Certificates Which Are About to Expire
============================================================

In the example below, Custodian will track SSL certificates which are in use by your Cloud SQL instances and notify about the ones which are going to expire in 60 days or less.

.. code-block:: yaml

    policies:
    - name: sql-ssl-cert
      description: |
        check basic work of Cloud SQL filter on SSL certificates: returns certs which are about to expire in 60 days or less
      resource: gcp.sql-ssl-cert
      filters:
        - type: value
          key: expirationTime
          op: less-than
          value_type: expiration
          value: 60
      actions:
        - type: notify
          to:
           - email@address
          # address doesnt matter
          format: txt
          transport:
            type: pubsub
            topic: projects/river-oxygen-233508/topics/first


  
