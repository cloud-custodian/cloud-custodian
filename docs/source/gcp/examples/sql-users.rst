Cloud SQL - Check Users
=======================

One of security best practices is to control list of your users with extended permissions (e.g. 'postgresql', 'root', etc). In the example below, Custodian lists existing users which are not included into an approved set.

.. code-block:: yaml

    policies:
    - name: sql-user
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
