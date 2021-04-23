Compute Engine - Delete Node Templates with Wrong Settings
==========================================================
Custodian can track and delete new Node Templates that are misconfigured.

In the example below, the policy checks if a Node Template has unbound ``cpus`` or ``memory`` usage in ``nodeTypeFlexibility``.

.. code-block:: yaml

    policies:
      - name: gcp-node-template-delete-with-wrong-type-flexibility
        resource: gcp.node-template
        mode:
          type: gcp-audit
          methods:
            - beta.compute.nodeTemplates.insert
        filters:
          - or:
              - type: value
                key: nodeTypeFlexibility.cpus
                value: any
              - type: value
                key: nodeTypeFlexibility.memory
                value: any
        actions:
          - type: delete
