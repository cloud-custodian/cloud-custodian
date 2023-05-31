.. _instancestoppublicipcompute:

Instance - Stop all the running instances with public IPs
=========================================================

The following example policy will stop all the running instances with public IPs and adds a tag

.. code-block:: yaml

    policies:
      - name: tag-stop-all-public-facing-instances
        description: |
          Tag and stop all the public IP instances
        resource: oci.instance
        filters:
          - type: value
            key: lifecycle_state
            value: 'RUNNING'
            op: eq
          - "additional_details.attachedVnics[*].publicIp": "not-null"
        actions:
          - type: update_instance
            params:
              update_instance_details:
                freeform_tags:
                  "public_facing": "true"
          - type: instance_action
            params:
              action: 'STOP'