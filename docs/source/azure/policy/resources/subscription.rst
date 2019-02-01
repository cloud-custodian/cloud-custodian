.. _azure_subscription:

Subscription
============

Filters
-------
- Standard Value Filter (see :ref:`filters`)
      - Model: `Subscription <https://docs.microsoft.com/en-us/python/api/azure-mgmt-subscription/azure.mgmt.subscription.models.subscription%28class%29?view=azure-python>`_

Actions
-------
- ``add-policy`` Add Azure Policy assignment for the subscrption
    - `name`: used as an assignment id
    - `display_name`: assignment display name
    - `definition_name`: Azure Policy definition id or display name
    - `scope`: default scope is the current subscription, you can extend it to the resource group or specific resource

Example Policies
----------------

This policy creates Azure Policy scoped to the current subscription if doesn't exist.

.. code-block:: yaml

    policies:
      - name: azure-policy-sample
        resource: azure.subscription
        filters:
          - type: missing
            policy: 
              resource: azure.policyassignments
              filters:
                - type: value
                  key: properties.displayName
                  op: eq
                  value_type: normalize
                  value: dn_sample_policy
        actions:
          - type: add-policy
            name: sample_policy
            display_name: dn_sample_policy
            definition_name: "Audit use of classic storage accounts"