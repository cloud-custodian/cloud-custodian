Cloud SQL - Check Database Names Against a Naming Convention
============================================================

The following example policies will allow you to control your Cloud SQL naming convention and check your instances for databases which names don't match that. A naming convention can be set up using standard regexp (regular expressions) syntax.

.. code-block:: yaml

    policies:
    - name: sql-database
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
