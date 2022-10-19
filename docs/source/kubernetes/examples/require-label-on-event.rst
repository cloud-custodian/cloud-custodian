Require Labels on Resources on Creation or Update
=================================================

Custodian can deny resources from being created or updated unless the resource
has the required labels. In the example below, we require that all pods
contain the recommended labels.

.. code-block:: yaml

  policies:
    - name: missing-recommended-labels
      mode:
        type: k8s-admission
        on-match: deny
        operations:
          - CREATE
          - UPDATE
      description: |
        Kubernetes recommmended the following labels from its docs:

        app.kubernetes.io/name
        app.kubernetes.io/instance
        app.kubernetes.io/version
        app.kubernetes.io/component
        app.kubernetes.io/part-of
        app.kubernetes.io/managed-by

        https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/
      resource: k8s.pod
      filters:
        - or:
          - metadata.labels."app.kubernetes.io/name": absent
          - metadata.labels."app.kubernetes.io/instance": absent
          - metadata.labels."app.kubernetes.io/version": absent
          - metadata.labels."app.kubernetes.io/component": absent
          - metadata.labels."app.kubernetes.io/part-of": absent
          - metadata.labels."app.kubernetes.io/managed-by": absent
