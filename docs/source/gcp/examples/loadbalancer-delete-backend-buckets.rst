Load Balancer - Delete backend buckets
=======================================

If a bucket was deleted it doesn't mean that appropriate backend buckets were deleted. The policy allow to delete backend buckets by the name of non-existing bucket.

.. code-block:: yaml

    policies:
      - name: gcp-loadbalancer-backend-buckets-delete
        resource: gcp.loadbalancer-backend-bucket
        filters:
          - type: value
            key: bucketName
            op: eq
            value: custodian-bucket-0
        actions:
          - type: delete
