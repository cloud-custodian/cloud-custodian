Restrict Service Account Usage
==============================

Custodian can restrict creation or updating of resources that specify
certain service accounts in their spec:

.. code-block:: yaml

  policies:
    - name: restrict-service-account-usage
      mode:
        type: k8s-admission
        on-match: deny
        operations:
          - CREATE
          - UPDATE
      resource: k8s.pod
      filters:
        - type: value
          key: spec.serviceAccountName
          value: "ClusterAdmin"
