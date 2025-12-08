.. _savingsplans:

Savings Plans
=============

The following example policy will query for all savings plans for your account.

.. code-block:: yaml

    policies:
    - name: query-all-savings-plans
        resource: savings-plans

The following example policy will find all active savings plans of the Compute
type.

.. code-block:: yaml

    policies:
    - name: active-compute-savings-plans
        resource: savings-plans
        filters:
        - type: value
            key: State
            value: active
        - type: value
            key: SavingsPlanType
            value: Compute
