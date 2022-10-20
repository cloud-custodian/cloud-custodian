Require Replicas on Deployments
================================

Require deployments to have at least 3 replicas


.. code-block:: yaml

  policies:
    - name: require-at-least-3-replicas
      resource: k8s.deployment
      mode:
        type: k8s-admission
        on-match: deny
        operations:
          - CREATE
          - UPDATE
      filters:
        - type: value
          key: spec.replicas
          value: 3
          op: gte
