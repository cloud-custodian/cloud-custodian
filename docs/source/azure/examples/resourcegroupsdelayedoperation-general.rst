.. _azure_example_delayedoperation:

Resource Groups - Delayed operations
====================================

You can use the ``mark-for-op`` action and the ``marked-for-op`` filter to implement 
delayed actions, such as delete a resource if it remains non-compliant for a few days.

This set of policies tags all empty resource groups with a special tag. If tagged 
group remains empty, it will be remove after 7 days. If the ``days`` field is omitted
the empty resource groups will be deleted immediately.

If resource group is no longer empty, tag is removed.

.. code-block:: yaml

  policies:
    - name: rg-mark-empty-for-deletion
      description: |
        Find any empty resource groups and mark for deletion in 7 days
      resource: azure.resourcegroup
      filters:
        - "tag:c7n_rg_empty": absent
        - type: empty-group
      actions:
        - type: mark-for-op
          tag: c7n_rg_empty
          op: delete
          days: 7

    - name: rg-unmark-if-not-empty
      resource: azure.resourcegroup
      description: |
        Remove the deletion tag from any resource group which now contain resources
        so it doesn't get deleted by the following policy
      filters:
        - "tag:c7n_rg_empty": not-null
        - not:
          - type: empty-group
      actions:
        - type: untag
          tags: ['c7n_rg_empty']

    - name: rg-delete-empty
      resource: azure.resourcegroup
      description: |
        Delete any marked resource groups which are empty
        if it has been that way for 7 days or more.
      filters:
        - type: marked-for-op
          tag: c7n_rg_empty
          op: delete
      actions:
        - type: delete
