Cloud SQL - Check Database Names Against a Naming Convention
============================================================

TBD. Return databases which names doesn't match a certain naming convention. Regexp is used.

In the example below, TBD.

.. code-block:: yaml

    - name: leonid-sql-database
      description: |
        check basic work of Cloud SQL filter on databases: return databases which names doesn't follow a certain naming convention
      resource: gcp.sql-database
      filters:
        - type: value
          key: name
          op: not-equal
          op: regex
          value: ^prod[-]{1}[a-z]*
      actions:
        - type: notify
          to:
           - email@address
          # address doesnt matter
          format: txt
          transport:
            type: pubsub
            topic: projects/river-oxygen-233508/topics/first
