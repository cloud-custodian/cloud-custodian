.. _instancestartdevinstancescompute:

Instance - Start all the stopped instances with a specific tag
==============================================================

The following example policy will start all the stopped instances that have freeform "custodian_dev" tag

.. code-block:: yaml

    policies:
      - name: start-all-stopped-dev-instances
        description: |
          Start all the stopped dev instances
        resource: oci.instance
        filters:
          - type: value
            key: lifecycle_state
            value: 'STOPPED'
            op: eq
          - type: value
            key: freeform_tags.custodian_dev
            value: 'true'
        actions:
          - start
