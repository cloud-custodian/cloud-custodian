Deployment Manager - Find expired deployments
=============================================
Custodian can check and delete deployments that have reached their expiration date which is in turn determined by your governance rules.

In the example below, the policy is set to delete deployments which were created more than 6 days ago.

.. code-block:: yaml

    policies:
      - name: expired-deployments
        description: Finds expired deployments
        resource: gcp.dm-deployment
        filters:
        - type: value
          key: insertTime
          value_type: expiration
          op: gte
          value: 7
        actions:
          - delete