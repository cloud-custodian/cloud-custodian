GCE - Force Usage of Specific Instance Templates
=======================================================
Custodian can enforce usage of only allowed instance templates for creation of instance groups.

In the example below, the policy checks if a newly created instance group uses an allowed instance template and deletes the group immediately if it doesn't.

.. code-block:: yaml

    vars:
      allowed-templates: &allowed-templates
        - https://www.googleapis.com/compute/v1/projects/mitrop-custodian/global/instanceTemplates/instance-template-1
        - https://www.googleapis.com/compute/v1/projects/mitrop-custodian/global/instanceTemplates/instance-template-2
    policies:
      - name: templates-restricted
        resource: gcp.instance-group-manager
        mode:
          type: gcp-audit
          methods:
            - v1.compute.instanceGroupManagers.insert
        filters:
          - type: value
            key: versions[].instanceTemplate
            op: difference
            value: *allowed-templates
        actions:
          - delete
