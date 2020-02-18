Compute Engine - Delete Instance Templates with Wrong Settings
==============================================================
Custodian can delete Instance Templates whose settings do not match the requirements.

In the example below, the policy checks if there are instance templates whose ``machineType`` setting is among the ``disallowed-machine-types``.

.. code-block:: yaml

    vars:
      # See https://cloud.google.com/compute/docs/machine-types
      disallowed-machine-types: &disallowed-machine-types
        - "f1-micro"
        - "g1-small"
        - "n1-highcpu-32"
        - "n1-highcpu-64"
        - "n1-highcpu-96"

    policies:
      - name: gcp-instance-template-delete-disallowed-machine-types
        resource: gcp.instance-template
        filters:
          - type: value
            key: properties.machineType
            op: in
            value: *disallowed-machine-types
        actions:
          - type: delete
