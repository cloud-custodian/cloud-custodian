Cloud SQL - Check Users
=======================

TBD. list instance superusers which are not included into a standard user set

In the example below, TBD.

.. code-block:: yaml

policies:
    - name: leonid-sql-user
      description: |
        check basic work of Cloud SQL filter on users: lists instance superusers which are not included into a standard user set
      resource: gcp.sql-user
      filters:
        - type: value
          key: name
          op: not-in
          value: [postgres, jamesbond]
      actions:
        - type: notify
          to:
           - email@address
          # address doesnt matter
          format: txt
          transport:
            type: pubsub
            topic: projects/river-oxygen-233508/topics/first
