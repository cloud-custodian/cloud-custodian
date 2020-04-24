ML Engine - Delete Models
=============================

Sometimes you may need to control geographical locations where your data and processing pipelines reside. 

The policy below automaticaly deletes all models which are deployed in regions specified in the black list.

.. code-block:: yaml

    policies:
      - name: ml-model-delete
        resource: gcp.ml-model
        filters:
          - type: value
            key: regions
            op: in
            value: [europe-west-1, europe-west4]
        actions:
          - type: delete
